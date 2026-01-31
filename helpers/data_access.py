_DRIVE_SERVICE: Optional[Any] = None


def _get_drive_service():
    global _DRIVE_SERVICE
    if _DRIVE_SERVICE is not None:
        return _DRIVE_SERVICE
    creds = _get_credentials()
    _DRIVE_SERVICE = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _DRIVE_SERVICE