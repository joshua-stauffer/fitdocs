"""Child process entry for the serve tests: configuration from the environment."""

import sys

from fitdocs_relay.config import load_config
from fitdocs_relay.serve import run_server

if __name__ == "__main__":
    sys.exit(run_server(load_config()))
