import database
from single_window_app import run


if __name__ == "__main__":
    database.connect()
    run()
