import sys
from experiment import main

if __name__ == "__main__":
    main(["baseline", *sys.argv[1:]])
