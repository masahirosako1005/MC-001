"""テストを手元の .env に左右されずに動かすためのテストランナー。

.env で本番相当 (DJANGO_DEBUG=0・DJANGO_SSL_REDIRECT=1) にしていると、テストクライアントの http の
リクエストがすべて https への 301 になってしまう。テストの間だけ HTTPS への転送を止める
(転送そのものは nginx 経由の確認と Django のミドルウェアの責務)。
キャッシュも MIKKE_CACHE (db / redis) によらず、テストごとに独立したメモリキャッシュにする。
静的ファイルも、collectstatic をしていなくても動くよう、名前にハッシュを付けない保存方法にする。
"""

from django.test.runner import DiscoverRunner
from django.test.utils import override_settings


class MikkeTestRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._overrides = override_settings(
            SECURE_SSL_REDIRECT=False,
            CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "mikke-test"}},
            STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                      "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
        )
        self._overrides.enable()

    def teardown_test_environment(self, **kwargs):
        self._overrides.disable()
        super().teardown_test_environment(**kwargs)
