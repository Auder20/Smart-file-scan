from app.models.file_info import FileCategory

_EXTENSION_MAP: dict[str, FileCategory] = {
    **dict.fromkeys(
        ["pdf", "doc", "docx", "odt", "txt", "md",
         "xls", "xlsx", "csv", "ppt", "pptx", "epub"],
        FileCategory.DOCUMENT
    ),
    **dict.fromkeys(
        ["jpg", "jpeg", "png", "gif", "bmp", "tiff",
         "webp", "svg", "ico", "heic", "psd"],
        FileCategory.IMAGE
    ),
    **dict.fromkeys(
        ["mp4", "mkv", "avi", "mov", "wmv", "flv", "webm"],
        FileCategory.VIDEO
    ),
    **dict.fromkeys(
        ["mp3", "wav", "flac", "aac", "ogg", "m4a"],
        FileCategory.AUDIO
    ),
    **dict.fromkeys(
        ["py", "java", "js", "ts", "html", "css",
         "c", "cpp", "cs", "go", "rs", "rb", "php",
         "sh", "json", "xml", "yaml", "yml", "sql"],
        FileCategory.CODE
    ),
    **dict.fromkeys(
        ["zip", "rar", "7z", "tar", "gz", "bz2"],
        FileCategory.ARCHIVE
    ),
    **dict.fromkeys(
        ["exe", "msi", "dll", "deb", "dmg", "jar"],
        FileCategory.EXECUTABLE
    ),
}


def classify_file(extension: str) -> FileCategory:
    return _EXTENSION_MAP.get(extension.lower(), FileCategory.OTHER)