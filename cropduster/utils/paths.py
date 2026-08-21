from cropduster.services.paths import unique_upload_dir


__all__ = ('get_upload_foldername',)


def get_upload_foldername(file_name, upload_to='%Y/%m'):
    """Deprecated alias for :func:`cropduster.services.paths.unique_upload_dir`."""
    return unique_upload_dir(file_name, upload_to)
