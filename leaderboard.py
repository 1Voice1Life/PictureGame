"""
Leaderboard
"""

from html import unescape
from xml.etree import ElementTree as ET

class Leaderboard:
    """
    A class that manages the leaderboard. Woo OOP!
    """

    _data = {}

    def __init__(self, subreddit, page="leaderboard"):
        """
        Public: Create/Load up a new Leaderboard.

        subreddit - A praw.objects.Subreddit. This should have the reddit
                    session available in it.
        page      - The optional location of the page in the wiki.

        Returns an instance of Leaderboard.
        """
        self.subreddit = subreddit
        self.page = page

    def _load(self):
        """
        Private: Get the raw HTML data from reddit. This object is not part of
          __init__ since it is lazily loaded. This would set _data to a dict,
          where the keys are the usernames and the values are arrays of round
          numbers won. It uses the html content rather than the markdown
          content, since it's computer-rendered and a bit more predictable.

        Returns nothing.
        """
        if not self._data:
            html_data = self.subreddit.get_wiki_page(self.page).content_html
            table = ET.XML(unescape(html_data)).find("table").find("tbody")
            self._data = dict(
                (row[1].text, row[2].text.split(", ")) for row in iter(table))

    def to_markdown(self, prepend="# Leaderboard\n\n"):
        """
        Internal: Returns a leaderboard table of the data in markdown, adding
          columns for rank and total wins.

        prepend - A string to prepend to the table. Defaults to title.

        Returns a Markdown String.
        """
        self._load()

        table = ("Rank | Username | Rounds won | Total |\n"
                 "|:--:|:--:|:--|:--:|:--:|\n")

        inv_map = {}
        for username, rounds in self._data.items():
            wins = len(rounds)
            inv_map[wins] = inv_map.get(wins, [])
            inv_map[wins].append(username)
        for rank, wins in enumerate(sorted(inv_map, reverse=True)):
            for username in inv_map[wins]:
                table += "{rank} | {username} | {rounds} | {total}\n".format(
                    rank=rank + 1, username=username,
                    rounds=", ".join(self._data[username]), total=wins)

        return prepend + table

    def add(self, user, roundno, publish=False):
        """
        Public: Add a user's win to the leaderboard.

        user    - A praw.objects.Redditor that won a round.
        roundno - An integer of the round the user won.
        publish - Whether or not to edit the wikipage after adding the win.

        Returns nothing.
        """
        self._load()

        self._data[user.name] = self._data.get(user.name, [])
        self._data[user.name].append(str(roundno))
        if publish:
            self.publish("{:s} won Round {:d}.".format(user.name, roundno))

    def remove(self, user, roundno, publish=False):
        """
        Public: Remove a user's win from the leaderboard.

        user    - A praw.objects.Redditor.
        roundno - An integer of the round to be removed.
        publish - Whether or not to edit the wikipage after removing the round.

        Returns nothing.
        """
        self._load()

        if self._data.get(user.name) and str(roundno) in self._data[user.name]:
            self._data[user.name].remove(str(roundno))
        if publish:
            self.publish("Discredit Round {:d} from {:s}.".format(roundno,
                                                                  user.name))

    def publish(self, reason="Added a Win."):
        """
        Internal: Publish any edits made to the wiki page.

        reason - The reason for the edit, usually for adding a win.

        Returns nothing.
        """
        self._load()
        self.subreddit.edit_wiki_page(self.page, self.to_markdown(),
                                      reason=reason)
