"""
Crawler implementation
"""
import datetime
import json
import os
import random
import re
import shutil
import time
from pathlib import Path
from typing import Pattern, Union

import requests
from bs4 import BeautifulSoup

import core_utils.constants as const
from core_utils.article.article import Article
from core_utils.article.io import to_raw, to_meta
from core_utils.config_dto import ConfigDTO


class IncorrectSeedURLError(Exception):
    """
    Raised when seed URL does not match standard pattern
    """


class NumberOfArticlesOutOfRangeError(Exception):
    """
    Raised when total number of articles is out of range from 1 to 150
    """


class IncorrectNumberOfArticlesError(Exception):
    """
    Raised when the total number of articles to parse is not an integer
    """


class IncorrectHeadersError(Exception):
    """
    Raised when headers are not in a form of dictionary
    """


class IncorrectEncodingError(Exception):
    """
    Raised when there is an invalid value for encoding
    """


class IncorrectTimeoutError(Exception):
    """
    Raised when timeout value is not a positive integer less than 60
    """


class IncorrectVerifyError(Exception):
    """
    Raised when the verify certificate value is invalid
    """


class Config:
    """
    Unpacks and validates configurations
    """

    def __init__(self, path_to_config: Path) -> None:
        """
        Initializes an instance of the Config class
        """
        self.path_to_config = path_to_config
        config_dto = self._extract_config_content()
        self._validate_config_content()
        self._seed_urls = config_dto.seed_urls
        self._num_articles = config_dto.total_articles
        self._headers = config_dto.headers
        self._encoding = config_dto.encoding
        self._timeout = config_dto.timeout
        self._should_verify_certificate = config_dto.should_verify_certificate
        self._headless_mode = config_dto.headless_mode

    def _extract_config_content(self) -> ConfigDTO:
        """
        Returns config values
        """
        with open(self.path_to_config, 'r', encoding='utf-8') as infile:
            reader = json.load(infile)
        return ConfigDTO(**reader)

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters
        are not corrupt
        """
        config_dto = self._extract_config_content()

        if not config_dto.seed_urls or not isinstance(config_dto.seed_urls, list):
            raise IncorrectSeedURLError

        for url in config_dto.seed_urls:
            if not isinstance(url, str) or not re.match(r'https?://.*/', url):
                raise IncorrectSeedURLError

        if (not isinstance(config_dto.total_articles, int)
                or isinstance(config_dto.total_articles, bool)
                or config_dto.total_articles < 1):
            raise IncorrectNumberOfArticlesError

        if config_dto.total_articles > const.NUM_ARTICLES_UPPER_LIMIT:
            raise NumberOfArticlesOutOfRangeError

        if not isinstance(config_dto.headers, dict):
            raise IncorrectHeadersError

        if not isinstance(config_dto.encoding, str):
            raise IncorrectEncodingError

        if (not isinstance(config_dto.timeout, int)
                or config_dto.timeout < const.TIMEOUT_LOWER_LIMIT
                or config_dto.timeout > const.TIMEOUT_UPPER_LIMIT):
            raise IncorrectTimeoutError

        if (not isinstance(config_dto.should_verify_certificate, bool)
                or not isinstance(config_dto.headless_mode, bool)):
            raise IncorrectVerifyError

    def get_seed_urls(self) -> list[str]:
        """
        Retrieve seed urls
        """
        return self._seed_urls

    def get_num_articles(self) -> int:
        """
        Retrieve total number of articles to scrape
        """
        return self._num_articles

    def get_headers(self) -> dict[str, str]:
        """
        Retrieve headers to use during requesting
        """
        return self._headers

    def get_encoding(self) -> str:
        """
        Retrieve encoding to use during parsing
        """
        return self._encoding

    def get_timeout(self) -> int:
        """
        Retrieve number of seconds to wait for response
        """
        return self._timeout

    def get_verify_certificate(self) -> bool:
        """
        Retrieve whether to verify certificate
        """
        return self._should_verify_certificate

    def get_headless_mode(self) -> bool:
        """
        Retrieve whether to use headless mode
        """
        return self._headless_mode


def make_request(url: str, config: Config) -> requests.models.Response:
    """
    Delivers a response from a request
    with given configuration
    """
    time.sleep(random.randrange(4, 7))
    response = requests.get(url,
                            timeout=config.get_timeout(),
                            headers=config.get_headers(),
                            verify=config.get_verify_certificate())
    response.encoding = config.get_encoding()
    return response


class Crawler:
    """
    Crawler implementation
    """

    url_pattern: Union[Pattern, str]

    def __init__(self, config: Config) -> None:
        """
        Initializes an instance of the Crawler class
        """
        self._seed_urls = config.get_seed_urls()
        self.config = config
        self.urls = []

    @staticmethod
    def _extract_url(article_bs: BeautifulSoup) -> str:
        """
        Finds and retrieves URL from HTML
        """
        link = article_bs.find('a')
        if link:
            href = link.get('href')
        else:
            href = None
        return href

    def find_articles(self) -> None:
        """
        Finds articles
        """
        start_url = self.config.get_seed_urls()[0]
        url = start_url
        count_of_page = 1
        while len(self.urls) < self.config.get_num_articles():
            print(url)
            page = make_request(url, config=self.config)
            page = page.content.decode(self.config.get_encoding())
            soup = BeautifulSoup(page, features="html.parser")
            h3_with_articles = soup.find_all('h3')
            for elem in h3_with_articles:
                url_ = self._extract_url(elem)
                if url_ is not None:
                    self.urls.append(url_)
                if len(self.urls) >= self.config.get_num_articles():
                    return
            count_of_page += 1
            url = f"{start_url}/page/{count_of_page}"

    def get_search_urls(self) -> list:
        """
        Returns seed_urls param
        """
        return self._seed_urls


class HTMLParser:
    """
    ArticleParser implementation
    """

    def __init__(self, full_url: str, article_id: int, config: Config) -> None:
        """
        Initializes an instance of the HTMLParser class
        """
        self.full_url = full_url
        self.article_id = article_id
        self.config = config
        self.article = Article(full_url, article_id)

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Finds text of article
        """
        div = article_soup.find('div', class_='entry-content')
        text = ''
        for p in div.find_all('p'):
            if 'Фото:' in p.text or re.search(r'\([0-9]+\+\)', p.text):
                break
            text += p.text
        self.article.text = text

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Finds meta information of article
        """
        div_date = article_soup.find('div', style='padding-left: 30px; padding-bottom: 10px;')
        self.article.date = self.unify_date_format(div_date.text)
        span_author = article_soup.find('span', class_='name')
        if span_author:
            a_author = span_author.find('a')
            if a_author:
                self.article.author = [a_author.text]
            else:
                self.article.author = ['NOT FOUND']

        title = article_soup.find('h1')
        self.article.title = title.text

    @staticmethod
    def unify_date_format(date_str: str) -> datetime.datetime:
        """
        Unifies date format
        """
        months_dict = {
            "января": "January",
            "февраля": "February",
            "марта": "March",
            "апреля": "April",
            "мая": "May",
            "июня": "June",
            "июля": "July",
            "августа": "August",
            "сентября": "September",
            "октября": "October",
            "ноября": "November",
            "декабря": "December"
        }
        date_list = date_str.split()
        month = months_dict[date_list[1]]
        date_list[1] = month
        date_str = ' '.join(date_list)
        return datetime.datetime.strptime(date_str, '%d %B %Y в %H:%M')

    def parse(self) -> Union[Article, bool, list]:
        """
        Parses each article
        """
        page = make_request(self.full_url, self.config)
        page.encoding = self.config.get_encoding()
        soup = BeautifulSoup(page.text, features="html.parser")
        print(self.full_url)
        self._fill_article_with_text(soup)
        self._fill_article_with_meta_information(soup)
        return self.article


def prepare_environment(base_path: Union[Path, str]) -> None:
    """
    Creates ASSETS_PATH folder if no created and removes existing folder
    """
    if base_path.exists():
        shutil.rmtree(base_path)
    os.makedirs(base_path)


def main() -> None:
    """
    Entrypoint for scrapper module
    """
    config = Config(const.CRAWLER_CONFIG_PATH)
    prepare_environment(const.ASSETS_PATH)
    crawler = Crawler(config)
    crawler.find_articles()
    for id_, url in enumerate(crawler.urls, 1):
        print(id_, url)
        parser = HTMLParser(full_url=url, article_id=id_, config=config)
        article = parser.parse()
        if isinstance(article, Article):
            to_raw(article)
            to_meta(article)


if __name__ == "__main__":
    main()
