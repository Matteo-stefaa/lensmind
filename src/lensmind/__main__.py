"""`lensmind` command: run the server with configuration from the environment."""

import uvicorn

from lensmind.api.app import create_app
from lensmind.settings import Settings


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
