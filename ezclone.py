import py_cui
import itertools
import os
import pyperclip
from py_cui.widgets import ScrollMenu, TextBox, ScrollTextBlock
from dotenv import load_dotenv
from github import Github
from github import Auth
from github import RateLimitExceededException


# Shennaningans
# Adding listener to a widget such that the content of the
# widget can update before the event is handled
ScrollMenu.old__init__ = ScrollMenu.__init__


def new__init__(self, id, title: str, grid: 'py_cui.grid.Grid',
                row: int, column: int, row_span: int, column_span: int,
                padx: int, pady: int, logger: 'py_cui.debug.PyCUILogger'):

    self.old__init__(id, title, grid, row, column, row_span,
                     column_span, padx, pady, logger)

    self.update_listeners = []


ScrollMenu.__init__ = new__init__

# Replace key
ScrollMenu.old_handle_key_press = ScrollMenu._handle_key_press


def new_handle_key_press(self, key_pressed: int):
    self.old_handle_key_press(key_pressed)

    for delegate in self.update_listeners:
        delegate()


ScrollMenu._handle_key_press = new_handle_key_press


# Add adders/removers
def add_listener(self, delegate):
    self.update_listeners.append(delegate)


def remove_listener(self, delegate):
    self.update_listeners.remove(delegate)


ScrollMenu.add_listener = add_listener
ScrollMenu.remove_listener = remove_listener


def pretty_repo(repo):
    return f"""
    Full name: {repo.full_name}
    Description: {repo.description}
    Date created: {repo.created_at}
    Date of last push: {repo.pushed_at}
    Home Page: {repo.homepage}
    Language: {repo.language}
    Number of forks: {repo.forks}
    Number of stars: {repo.stargazers_count}
    URL: {repo.html_url}
    """


def get_priv_repos(g: Github) -> list:
    repos = g.get_user().get_repos()
    page = 0

    while True:
        try:
            repo_page = repos.get_page(page)
            if not repo_page:
                break

            for repo in repo_page:
                yield repo
            page += 1
        except RateLimitExceededException:
            print("Rate limit exceeded. Waiting for reset...")

    return repos


def get_pub_repos(g: Github, query):
    repos = g.get_user().get_repos()
    page = 0

    while True:
        try:
            repo_page = repos.get_page(page)
            if not repo_page:
                break

            for repo in repo_page:
                yield repo
            page += 1
        except RateLimitExceededException:
            print("Rate limit exceeded. Waiting for reset...")

    return repos


def init_github():
    load_dotenv()
    github_token = os.getenv("GITHUB_ACCESS_TOKEN")

    print("Github Token:", github_token)
    auth = Auth.Token(github_token)
    g = Github(auth=auth)

    return g


class GithubSearchWidget:
    def __init__(self, master: py_cui.PyCUI):
        self.g = init_github()
        self.repos = []
        self.page = 0
        self.query = ""

        self.master: py_cui.PyCUI = master
        self.master.toggle_unicode_borders()

        # Create search bar
        self.search_bar: TextBox = self.master.add_text_box(
            'Search', 0, 0)

        self.search_bar.add_key_command(
            py_cui.keys.KEY_ENTER,
            lambda: self.search(self.search_bar.get()))

        self.search_bar.add_key_command(
            py_cui.keys.KEY_TAB, self.select_next_widget)

        # Setup search results
        self.list_box: ScrollMenu = self.master.add_scroll_menu(
            "Page 1", 1, 0, row_span=7, column_span=1)

        self.list_box.add_key_command(
            py_cui.keys.KEY_TAB, self.select_next_widget)

        self.list_box.add_key_command(
            py_cui.keys.KEY_X_LOWER,
            lambda: self.copy_github_url(self.list_box.get()))

        self.list_box.add_key_command(
            py_cui.keys.KEY_RIGHT_ARROW,
            lambda: self.next_page())

        self.list_box.add_key_command(
            py_cui.keys.KEY_LEFT_ARROW,
            lambda: self.prev_page())

        self.list_box.add_key_command(
            py_cui.keys.KEY_L_LOWER,
            lambda: self.next_page())

        self.list_box.add_key_command(
            py_cui.keys.KEY_H_LOWER,
            lambda: self.prev_page())

        self.list_box.add_key_command(
            py_cui.keys.KEY_K_LOWER,
            self.list_box._scroll_up)

        self.list_box.add_key_command(
            py_cui.keys.KEY_J_LOWER,
            lambda: self.list_box._scroll_down(
                self.list_box.get_viewport_height()))

        self.list_box.add_listener(self.update_info_box)

        # Setup info info block
        self.info_box: ScrollTextBlock = self.master.add_text_block(
            "Info", 1, 1, row_span=7, column_span=1)

        self.info_box.add_key_command(
            py_cui.keys.KEY_TAB, self.select_next_widget)

        # Setup TAB cycling
        self.widgets = itertools.cycle(
            [self.search_bar, self.list_box])
        self.master.move_focus(next(self.widgets))

    def select_next_widget(self):
        self.master.move_focus(next(self.widgets))

    def search(self, query: str):
        self.page = 0
        self.query = query
        self.list_box_populate()
        self.select_next_widget()

    def next_page(self):
        self.page += 1
        self.list_box_populate()

    def prev_page(self):
        self.page -= 1
        if self.page < 0:
            self.page = 0

        self.list_box_populate()

    def update_info_box(self):
        selected_entry = self.list_box.get()
        if selected_entry:
            index = selected_entry.split(":")[0]
            index = int(index)
            try:
                repo = self.repos[index]
                self.info_box_populate(repo)
            except Exception as e:
                print(f"[ERROR] update_info_box: {e}")

    def list_box_populate(self):
        self.list_box.clear()
        self.repos = []

        repos = self.g.search_repositories(self.query)
        try:
            repo_page = repos.get_page(self.page)

            index = 0
            for repo in repo_page:
                self.list_box.add_item(f"{index}: {repo.full_name}")
                self.repos.append(repo)
                index += 1

            self.list_box.set_title(f"Page {self.page+1}/-")

            self.master.move_focus(self.list_box)

            if len(self.repos) > 0:
                self.info_box_populate(self.repos[0])
        except Exception:
            if self.page > 1:
                self.page -= 1

    def info_box_populate(self, repo):
        self.info_box.set_text(pretty_repo(repo))

    def copy_github_url(self, input_info):
        index = input_info.split(":")[0]
        index = int(index)
        pyperclip.copy(self.repos[index].html_url)
        self.master.stop()


if __name__ == "__main__":
    root = py_cui.PyCUI(8, 2)
    s = GithubSearchWidget(root)
    root.start()

