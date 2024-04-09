import subprocess
from dotenv import load_dotenv
from sys import argv


if __name__ == "__main__":
    load_dotenv()
    args: list[str] = ["litestar", "--app", "chronicler.app:app", "run"]
    args.extend(argv[1:])
    subprocess.run(args)
