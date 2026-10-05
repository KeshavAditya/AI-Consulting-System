from wiki import get_page, find_short_path
import random
import warnings
import nltk
import spacy
import wikipedia


def random_page(common_words):
    """Pick a random starting page that actually resolves on Wikipedia."""
    while True:
        word = random.choice(common_words)
        try:
            return get_page(word)
        except wikipedia.exceptions.PageError:
            # the word matched no article, so just try another one
            continue


def prompt_for_page():
    """Ask the user for a page until they name one that resolves."""
    while True:
        name = input()
        try:
            return get_page(name)
        except wikipedia.exceptions.PageError:
            print("Couldn't find that page. Try another one.")


def bacon_path(start_page, end_page):
    """Find a path, or None if the search times out or finds nothing."""
    try:
        return find_short_path(start_page, end_page)
    except TimeoutError:
        return None


def main():
    print("\n\n🥓 Welcome to WikiBacon! 🥓\n")
    print("In this game, we start from a random Wikipedia page, and then we compete to see who can name a page that is *farthest away* from the original page.\n")
    print("Ready to play? Hit Enter to start, or type 'q' to quit")
    cmd = input()
    if cmd == "q":
        return
    
    with open("dictionary.txt", "r") as f:
        common_words = f.read().splitlines()

    while True:

        start_page = random_page(common_words)
        print(f"The starting page is: {start_page.title}\n")
        print(f"Summary: {start_page.summary[:500]}...\n")


        computer_page = random_page(common_words)
        print(f"The computer's page is: {computer_page.title}\n")
        print(f"Summary: {computer_page.summary[:500]}...\n")

        print("What would you like your page to be page?")
        user_page = prompt_for_page()
        print(f"Your page is: {user_page.title}\n")
        print(f"Summary: {user_page.summary[:500]}...\n")

        print("Calculating Bacon paths...\n")

        computer_path = bacon_path(start_page, computer_page)
        user_path = bacon_path(start_page, user_page)

        # one of the searches may give up, so don't try to score a missing path
        if computer_path is None or user_path is None:
            print("Couldn't find a path for one of the pages this round.\n")
        else:
            print("Computer's path:")
            print(f"\n -> ".join(computer_path))
            print(f"Length: {len(computer_path)}\n")

            print("Your path:")
            print(f"\n -> ".join(user_path))
            print(f"Length: {len(user_path)}\n")

            if len(computer_path) > len(user_path):
                print("I win!")
            elif len(computer_path) < len(user_path):
                print("You win!")
            else:
                print("It's a tie!")

        print("\n\nPlay again? Hit Enter for another round, or type 'q' to quit")
        cmd = input()
        if cmd == "q":
            print("\n🥓 Thanks for playing! 🥓\n")
            print("WikiBacon is not affiliated with Wikipedia or the Wikimedia Foundation. To donate to Wikipedia and support their vision of an open internet that makes games like this possible, please visit https://donate.wikimedia.org/\n")
            return

if __name__ == "__main__":
    main()