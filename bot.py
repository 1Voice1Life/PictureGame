"""
PictureGameBot by /u/Mustermind
Requested by /u/malz_ for /r/PictureGame

Pretty much my magnum opus when it comes to my bot-making skills.

Requirements:
- A subreddit where only the player account can post.
- A bot account that moderates posts (must be a moderator)
- A player account that is passed from person to person.
- A wiki with the pages "leaderboard" and "accounts" with prepopulated content.
"""

import os
import re
import sys
import praw
import time
import base64
import pyimgur
import requests
from random import choice as sample
from urllib.request import urlretrieve

import warnings
warnings.filterwarnings("ignore", category=ResourceWarning)

from picturegamebot.leaderboard import Leaderboard


def minutes_passed(thing, minutes):
    """
    Internal: Returns True if said minutes have passed since the creation
      of said thing.

    thing   - An object with a 'created_utc' attribute.
    minutes - Number of minutes to have passed.
 
    Returns a Boolean.
    """
    if thing:
        return time.time() > (thing.created_utc + (minutes*60))


class PictureGameBot:
    """
    Main runner for the picturegamebot.
    """
    version = "1.0"
    user_agent = "PictureGame Approver"

    def __init__(self, gamebot=(None, None), imgurid=None,
                 subreddit="PictureGame"):
        """
        Public: Logs into the bot and the player account. Sets up imgur
          access.

        gamebot   - A tuple of username and password for the bot account.
        imgurid   - The Client ID used to log into Imgur.
        subreddit - The subreddit to listen on.

        Returns an instance of PictureGameBot.
        """
        self.gamebot = (os.environ.get("REDDIT_USERNAME", gamebot[0]),
                        os.environ.get("REDDIT_PASSWORD", gamebot[1]))
        self.r_gamebot = praw.Reddit("{:s}, v{:s}".format(self.user_agent,
                                                          self.version))
        self.r_gamebot.login(self.gamebot[0], self.gamebot[1])

        self.subreddit = self.r_gamebot.get_subreddit(subreddit)

        self.imgur = pyimgur.Imgur(os.environ.get("IMGUR_ID", imgurid))

        self.leaderboard = Leaderboard(self.subreddit)



    def latest_round(self):
        """
        Internal: Gets the top post in a subreddit that starts with "[Round".

        Returns a praw.objects.Submission.
        """
        new = self.subreddit.get_new()
        return next(post for post in new if re.search(r"^\[Round", post.title,
                                                      re.IGNORECASE))

    def increment_flair(self, user, curround):
        """
        Internal: Add the current win to the player's flair. If the player
          has more than 7 wins, sets the flair to "X wins", else adds the
          current round number to the flair.

        NOTE: Any additional flair (e.g. "Fair Play Award" or "Official
          PictureGame Critic") will only work with the wins format. For
          example, the mods must change "Round 1234, 2345" to "2 wins" before
          adding a "Difficult Question Asker" to the end of it.

        user     - A praw.objects.Redditor.
        curround - The round number that the user just won.

        Returns nothing.
        """
        flair = self.subreddit.get_flair(user)
        if flair is not None:
            text = flair["flair_text"]
            if text == "" or text is None:
                self.subreddit.set_flair(user, "Round {:d}".format(curround),
                                         "winner")
            elif re.search(r"\d+ wins", text):
                repl = re.sub(
                    r"(\d+) wins",
                    lambda m: "{:d} wins".format(int(m.group(1)) + 1),
                    text)
                self.subreddit.set_flair(user, repl, "winner")
            elif re.search(r"^Round", text):
                rounds = len(re.findall(r"(\d+)", text))
                if rounds >= 7:
                    self.subreddit.set_flair(user,
                                             "{:d} wins".format(rounds + 1),
                                             "winner")
                else:
                    self.subreddit.set_flair(
                        user,
                        "{:s}, {:d}".format(text, curround), "winner")

    def winner_comment(self, post):
        """
        Internal: Get the comment that gave the correct answer (because it
          was replied with "+correct" by the r_player account).

        post - A praw.objects.Submission object.

        Returns a praw.objects.Comment.
        """
        post.replace_more_comments(limit=None)
        comments = praw.helpers.flatten_tree(post.comments)
        for comment in comments:
            if (isinstance(comment, praw.objects.Comment)
                and (comment.author == post.author or comment.author in self.subreddit.get_moderators())
                and "+correct" in comment.body
                and not comment.is_root):
                parent = self.r_gamebot.get_info(thing_id=comment.parent_id)
                if (parent.author is not None
                        and parent.author != post.author):
                    return parent

    def already_replied(self, comment):
        """
        Internal: Says whether the given comment already has a reply from the
          bot. This is meant to be used as a backup to avoid granting the
          same player two wins.

        comment - The comment to check the replies to.

        Returns a Boolean.
        """
        for reply in comment.replies:
            if reply.author == self.r_gamebot.user:
                return True

    def warn_nopost(self, op_=None):
        """
        Internal: Warn the account and the op, if possible, that the account
          will be reset if he doesn't create a post in 30 minutes.

        op_ - An optional other person who holds the account.

        Returns nothing.
        """
        subject = "You haven't submitted a post!"
        text = (
            "It seems that 30 minutes have passed since you won the "
            "last round. Please upload a post in the next 15 minutes."
        )
        if op_:
            self.r_gamebot.send_message(op_, subject, text)
        self.r_gamebot.send_message(self.r_player.user, subject, text)

    def warn_noanswer(self, op_=None):
        """
        Internal: Warn the account and the op, if possible, that the account
          will be reset if his question isn't answered in 30 minutes.

        op_ - An optional other person who holds the account.

        Returns nothing.
        """
        subject = "You haven't gotten an answer!"
        text = (
            "It seems that 2.5 hours have passed since you submitted your "
            "round. Try giving hints, or if "
            "you already gave out a few hints, try and make them easier."
        )
        if op_:
            self.r_gamebot.send_message(op_, subject, text)


    def win(self, comment):
        """
        Internal: So somebody got the right answer. First, add a win to his
          flair. Then, congratulate the winner and send him the resetted
          password via private message.

        comment - The winning comment.

        Regrets nothing.
        """
        comment.reply(
            "Congratulations, that was the correct answer! Please continue the "
            "game as soon as possible. You have been PM'd the instructions for "
            "continuing the game."
            "\n\n---\n^^I ^^am ^^a ^^bot. ^^If ^^I ^^don't ^^work, ^^please "
            "[^^PM ^^my ^^master](http://www.reddit.com/message/compose/?to=tara1) "
            "^^or [^^message ^^the ^^moderators.](http://www.reddit.com/message/compose?to=%2Fr%2FPictureGame)"
        ).distinguish()
        curround = int(re.search(r"^\[round (\d+)",
                                 comment.submission.title.lower())
                       .group(1))
        self.increment_flair(comment.author, curround)
        comment.submission.set_flair("ROUND OVER", "over")
        subject = "Congratulations, you can post the next round!"
        text = (
            "    Congratulations on winning the last round! "
            "\n\n    Your account should now be approved to submit to /r/PictureGame "
            "to submit a new round. "
            "\n\n    Please remember that your title must start with \"[Round {roundno!s}]\"."  
            "\n\n    Please share how you got the answer in the comments. "            
            "\n\n\> [Submit a new Round]"
            "(http://www.reddit.com/r/PictureGame/submit?title=[Round%20{roundno!s}]) "
            "\n\n---\n^First ^time ^winning? ^See ^the "
            "[^hosting ^guide](/r/picturegame/wiki/hosting)"          
        ).format(roundno=curround + 1)
        self.r_gamebot.send_message(comment.author, subject, text)
        self.subreddit.add_contributor(comment.author)
        self.leaderboard.add(comment.author, curround, publish=True)

    def run(self):
        """
        Public: Starts listening in the subreddit and does its thing.
          My complicated logic in plain English:

          if LATEST POST IS UNSOLVED:
            if POST HAS ANSWER:
              send instructions to winner and approve them to the sub
              remove the old OP
              chill for a bit
            or else:
              if 150 MINUTES HAVE PASSED AND I HAVEN'T WARNED YET:
                pm OP that he needs to provide hints before 30 minutes
              if 180 MINUTES HAVE PASSED AND I WARNED YA:
                set the flair to ABANDONED
                chill for a bit
                (the bot will upload a new post next loop)

          or else if LATEST POST HAS BEEN SOLVED:
            if 30 MINUTES HAVE PASSED AND I HAVEN'T WARNED YET:
              pm OP that he needs to put a new post up before 15 minutes
            if 45 MINUTES HAVE PASSED AND I WARNED YA:
              the bot will upload a new post

          or else if LATEST POST HAS BEEN KILLED (DEAD ROUND/ABANDONED):
            the bot will upload a new post

        Returns nothing, it's a looping function.
        """
        nopost_warning = False    # Warn if the user posts nothing for an hour.
        noanswer_warning = False  # Warn if unsolved in 90 mins of posting.
        current_op = None         # The person who owns the account. (optional)
        while True:
            try:
                latest_round = self.latest_round()
                winner_comment = self.winner_comment(latest_round)
                link_flair = latest_round.link_flair_text

                if (link_flair is None
                            or link_flair == ""
                            or re.search(link_flair, "UNSOLVED",
                                         re.IGNORECASE)):
                    nopost_warning = False
                    if (winner_comment
                            and not self.already_replied(winner_comment)):
                        print("New winner! PMing info.")
                        self.win(winner_comment)
                        self.subreddit.remove_contributor(current_op)
                        current_op = winner_comment.author
                        noanswer_warning = False
                        time.sleep(60)

            except requests.exceptions.HTTPError as error:
                if error.response.status_code in [429, 500, 502, 503, 504]:
                    print("Reddit is {:d}ing! Powering through...".format(
                        error.response.status_code
                    ))
            except praw.errors.RateLimitExceeded as error:
                print("Ratelimit: {:d} seconds".format(error.sleep_time))
                time.sleep(error.sleep_time)
