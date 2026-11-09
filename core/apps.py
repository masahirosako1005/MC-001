from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"
    verbose_name = "共通"

    def ready(self) -> None:
        from . import signals  # noqa: F401
