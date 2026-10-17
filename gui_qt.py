"""Launch Sky Macro Player (compatibility entry point for start.vbs)."""

from macro_player.app import (
    INSTANCE_SERVER,
    acquire_instance_lock,
    install_instance_server,
    main,
    request_existing_instance,
)

__all__ = [
    "INSTANCE_SERVER", "acquire_instance_lock", "install_instance_server", "main",
    "request_existing_instance",
]

if __name__ == "__main__":
    raise SystemExit(main())
