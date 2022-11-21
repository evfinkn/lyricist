import os
import re
import json
import time
import argparse
import itertools
import dataclasses
import unicodedata
from typing import ClassVar

import bs4
import requests


def _remove_punctuation(string):
    """
    Removes punctuation from a string.
    
    Parameters
    ----------
    string : str
        The string to remove punctuation from.
        
    Returns
    -------
    str
        `string` without punctuation.
        
    """
    return re.sub(r"[^\w\s]", "", string)


@dataclasses.dataclass
class Artist:
    """An artist from the Genius API."""
    
    _artists: ClassVar[dict[int, "Artist"]] = {}
    
    id: int
    name: str
    url: str
    # repr=False because repr for Song contains Artist, so this would cause an infinite loop
    songs: list["Song"] = dataclasses.field(default_factory=list, init=False, repr=False)
    featured_on: list["Song"] = dataclasses.field(default_factory=list, init=False, repr=False)
    
    @classmethod
    def from_data(cls, data):
        """
        Creates a `Artist` from the dict returned by a Genius API request for an artist.
        
        """
        id_ = data["id"]  # id_ because "id" is built-in keyword
        if id_ in cls._artists:
            return cls._artists[id_]
        name = data["name"]
        url = data["url"]
        artist = cls(id_, name, url)
        cls._artists[id_] = artist
        return artist
    
    # def __str__(self):
    #     return self.name
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url
        }
    
    def save(self, file_path):
        obj = self.to_dict()
        obj["time"] = time.time()
        song_dicts = []
        for song in self.songs:
            song_dicts.append(song.to_dict())
        obj["songs"] = song_dicts
        featured_on_dicts = []
        for song in self.featured_on:
            featured_on_dicts.append(song.to_dict())
        obj["featured_on"] = featured_on_dicts
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(obj, file)
            

@dataclasses.dataclass
class Song:
    """A song from the Genius API."""
    
    _songs: ClassVar[dict[int, "Song"]] = {}
    
    id: int
    title: str
    full_title: str
    url: str
    artist: "Artist"
    featured_artists: list["Artist"] = dataclasses.field(default_factory=list)
    lyrics: str = dataclasses.field(default=None, init=False)
    
    @classmethod
    def from_data(cls, data):
        """
        Creates a `Song` from the dict returned by a Genius API request for a song.
        
        """
        id_ = data["id"]  # id_ because "id" is built-in keyword
        if id_ in cls._songs:
            return cls._songs[id_]
        title = unicodedata.normalize("NFKD", data["title"])
        full_title = unicodedata.normalize("NFKD", data["full_title"])
        url = data["url"]
        artist = Artist.from_data(data["primary_artist"])
        featured_artists = []
        for artist_data in data["featured_artists"]:
            featured_artists.append(Artist.from_data(artist_data))
            
        song = cls(id_, title, full_title, url, artist, featured_artists)
        song.artist.songs.append(song)
        for featured_artist in song.featured_artists:
            featured_artist.featured_on.append(song)
        cls._songs[id_] = song
        return song
    
    def __str__(self):
        return self.full_title
    
    def to_dict(self):
        featured_artists_dicts = []
        for featured_artist in self.featured_artists:
            featured_artists_dicts.append(featured_artist.to_dict())
        return {
            "id": self.id,
            "title": self.title,
            "full_title": self.full_title,
            "url": self.url,
            "primary_artist": self.artist.to_dict(),
            "featured_artists": featured_artists_dicts,
            "lyrics": self.lyrics
        }
    

class GeniusRequester:
    """A class that handles requests to the Genius API."""
    
    WEB_URL = "https://genius.com"
    API_URL = "http://api.genius.com"
    
    def __init__(self, access_token=None):
        if access_token is None:
            access_token = os.environ.get("GENIUS_ACCESS_TOKEN")
        if not access_token:
            raise ValueError("Lyricist requires an access token")
        
        self._session = requests.Session()
        self._session.headers = {"User-Agent": "Lyricist"}
        self._header = {"Authorization": f"Bearer {access_token}"}
        
    def request(self, path, method="GET", params=None, web=False):
        if path.startswith("/"):
            path = path[1:]
        if params is None:
            params = {}
        
        if web:
            url = f"{GeniusRequester.WEB_URL}/{path}"
        else:
            url = f"{GeniusRequester.API_URL}/{path}"
        
        res = self._session.request(method, url, params=params, headers=self._header)
        if web:
            return res.text
        elif res.status_code != 200:
            raise Exception("Request status code is not 200")
        res = res.json()
        return res.get("response", res)
    

class Lyricist:
    
    def __init__(self, access_token=None):
        self._requester = GeniusRequester(access_token)
        
    def get_artist_genius_name(self, alias):
        """Gets the name used by Genius for an artist.
        
        Artists on Genius can have aliases. For example, the names "Mary Kate & Ashley Olsen,"
        "Olsen Twins," and "Mary-Kate And Ashley" all refer to the same artist. However, the
        Genius API uses only 1 of these to refer to an artist. Given an alias, this method
        returns the name Genius uses for the artist with that alias.
        
        Parameters
        ----------
        alias : str
            An alias an artist is referred to by.
        
        Returns
        -------
        str
            The name Genius uses to refer to the artist referred to by `alias`.
            
        Examples
        --------
        >>> lyricist = Lyricist()
        >>> lyricist.get_artist_genius_name('Olsen Twins')
        'Mary Kate & Ashley Olsen'
        >>> lyricist.get_artist_genius_name('Tina Snow')
        'Megan Thee Stallion'
        
        """
        alias = _remove_punctuation(alias)
        path = f"artists/{alias.replace(' ', '-')}"
        res = self._requester.request(path, web=True)
        html = bs4.BeautifulSoup(res, "html.parser")
        # element that contains the text for the artist's "canonical" name
        h1 = html.select("h1.profile_identity-name_iq_and_role_icon")[0]
        # h1.text includes lot of whitespace surrounding the actual name, stripped_strings removes these
        # stripped_strings is a generator though, so have to convert it to a list and get the first item
        return list(h1.stripped_strings)[0]
        
    def get_artist_id(self, name):
        """
        Gets the id used by Genius for an artist.
        
        Internally, every artist on Genius is assigned a unique id. The Genius API uses these ids
        (instead of names) to get info about an artist.
        
        Parameters
        ----------
        name: str
            The name of the artist to get the id of.
        
        Returns
        -------
        int
            The id for artist `name`.
        
        Raises
        ------
        ValueError
            If can't find the id for artist `name`.
        
        Examples
        --------
        >>> lyricist = Lyricist()
        >>> lyricist.get_artist_id('Nicki Minaj')
        92
        >>> lyricist.get_artist_id('Richard D. James')
        38515
        
        """
        name = self.get_artist_genius_name(name)
        name_no_punc = _remove_punctuation(name)
        path = f"artists/{name_no_punc.replace(' ', '-')}"
        res = self._requester.request(path, web=True)
        html = bs4.BeautifulSoup(res.replace("<br/>", "\n"), "html.parser")
        songs = html.find_all(
            "preload-content", 
            attrs={"data-preload_data": re.compile("{\"artist_songs\":\[")}
        )[0]
        songs = json.loads(songs.attrs["data-preload_data"])["artist_songs"]
        for song in songs:
            primary_artist = song["primary_artist"]
            if primary_artist["name"] == name:
                return primary_artist["id"]
            for featured_artist in song["featured_artists"]:
                if featured_artist["name"] == name:
                    return featured_artist["id"]
        
        # if no id returned yet, artist's songs on their page are songs produce by them, i.e.
        # A. G. Cook isn't the primary artist nor featured artist on any of the songs on his page
        # in this case, try to get the id from the search results of the artist's name
        res = self._requester.request("search", params={"q": name})
        for hit in res["hits"]:
            primary_artist = hit["result"]["primary_artist"]
            if primary_artist["name"] == name:
                return primary_artist["id"]
            for featured_artist in song["featured_artists"]:
                if featured_artist["name"] == name:
                    return featured_artist["id"]
            
        raise ValueError(f"Couldn't get the id for {name}")
        
    def get_artist_from_name(self, name):
        """
        Gets the `Artist` with the given name.
        
        Parameters
        ----------
        name : str
            The name of the artist to get.
            
        Returns
        -------
        Artist
            The artist with the name `name`.
            
        Examples
        --------
        >>> lyricist = Lyricist()
        >>> lyricist.get_artist_from_name('Charli XCX')
        Artist(id=45349, name='Charli XCX', url='https://genius.com/artists/Charli-xcx')
        
        """
        artist_id = self.get_artist_id(name)
        return self.get_artist_from_id(artist_id)
    
    def get_artist_from_id(self, artist_id):
        """
        Gets the `Artist` with the given id.
        
        Parameters
        ----------
        artist_id : int
            The id of the artist to get.
            
        Returns
        -------
        Artist
            The artist with the id `artist_id`.
            
        Examples
        --------
        >>> lyricist = Lyricist()
        >>> lyricist.get_artist_from_id(45349)
        Artist(id=45349, name='Charli XCX', url='https://genius.com/artists/Charli-xcx')
        
        """
        path = f"/artists/{artist_id}"
        data = self._requester.request(path)
        return Artist.from_data(data["artist"])
    
    def get_artist_songs(self, artist):
        path = f"artists/{artist.id}/songs"
        page = 1
        while page is not None:
            res = self._requester.request(path, params={"per_page": 50, "page": page})
            page = res["next_page"]
            for song_data in res["songs"]:
                song = Song.from_data(song_data)
    
    def get_song_lyrics(self, song):
        if song.lyrics is None:
            try:
                html = self._requester.request(song.url, web=True)
                html = bs4.BeautifulSoup(re.sub(r"(<br>)|(<br\/>)", "\n", html), "html.parser")
                div = html.select("div[data-lyrics-container='true']")[0]
                lyrics = div.get_text()
                lyrics = unicodedata.normalize("NFKD", lyrics)  # replaces unicode characters like \u2005 with plain equivalents
                lyrics = re.sub(r"(\[.*?\])\n{1}", "", lyrics)  # remove headers (i.e. "[Chorus]")
                lyrics = lyrics.replace("\n\n", "\n")
                lyrics = _remove_punctuation(lyrics)
                lyrics = lyrics.casefold()
                song.lyrics = lyrics
            except Exception:
                song.lyrics = ""
        return song.lyrics
    
    def get_artist_lyrics(self, artist):
        for song in itertools.chain(artist.songs, artist.featured_on):
            self.get_song_lyrics(song)
            
    def search_artist_lyrics(self, artist, lyrics, featured=True, match_all=False):
        if isinstance(lyrics, str):
            lyrics = [lyrics]
        # convert lyrics to lowercase and remove punctuation to make searching easier
        lyrics = [_remove_punctuation(lyric.casefold()) for lyric in lyrics]
        # don't want to change artist.songs so create shallow copy with list(artist.songs)
        all_songs = list(artist.songs)
        if featured:
            all_songs.extend(artist.featured_on)
        matches = []
        has_lyrics = all if match_all else any
        for song in all_songs:
            if song.lyrics == "":
                continue  # skip song because nothing to search
            if has_lyrics([lyric in song.lyrics for lyric in lyrics]):
                matches.append(song)
        return matches
    
    def save_artist(self, artist, save_dir):
        file_path = f"{save_dir}/{artist.id}.json"
        artist.save(file_path)
        
    def is_id_saved(self, artist_id, save_dir):
        file_path = f"{save_dir}/{artist_id}.json"
        return os.path.exists(file_path)
        
    def load_artist(self, artist_id, save_dir):
        file_path = f"{save_dir}/{artist_id}.json"
        with open(file_path, encoding="utf-8") as file:
            artist_json = json.load(file)
        artist = Artist.from_data(artist_json)
        for song_json in itertools.chain(artist_json["songs"], artist_json["featured_on"]):
            song = Song.from_data(song_json)
            song.lyrics = song_json["lyrics"]
        return artist
    
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="lyricist",
        description="Search for a lyric in an artist's songs")
    parser.add_argument(
        "artist",
        help="The name (or id if --id is specified) of the artist whose songs you'd like to search")
    parser.add_argument(
        "lyric",
        nargs="+",
        help=("The lyric to search for. If provided multiple, the artist's songs that contain ANY "
              "of the lyrics are returned (unless --all is specified)"))
    parser.add_argument(
        "-t",
        "--token",
        help=("The access token to use for Genius API requests. If not provided, it is retrieved "
              "from the \"GENIUS_ACCESS_TOKEN\" environment variable"))
    parser.add_argument(
        "--id",
        action="store_true",
        help="The passed in artist will be interpreted as the artist's id instead of their name")
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="A song must contain ALL of the lyrics passed in to be matched")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        help="Print debugging information")
    
    args = parser.parse_args()
    verbose = args.verbose
    
    # https://stackoverflow.com/a/595315
    script_dir = os.path.dirname(os.path.realpath(__file__))  # directory called from
    save_dir = f"{script_dir}/artists"
    
    lyricist = Lyricist(args.token)
    
    if not args.id:
        if verbose:
            print("Getting artist id")
        artist_id = lyricist.get_artist_id(args.artist)
        if verbose:
            print(f"Artist id is {artist_id}")
    else:
        artist_id = args.artist
    if lyricist.is_id_saved(artist_id, save_dir):
        if verbose:
            print("Loading artist from saved JSON")
        artist = lyricist.load_artist(artist_id, save_dir)
    else:
        if verbose:
            print("Artist is not saved. Getting artist and songs")
        artist = lyricist.get_artist_from_id(artist_id)
        lyricist.get_artist_songs(artist)
        lyricist.get_artist_lyrics(artist)
        lyricist.save_artist(artist, save_dir)
    
    matches = lyricist.search_artist_lyrics(artist, args.lyric, match_all=args.all)
    for song in matches:
        print(song.full_title)
