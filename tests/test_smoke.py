"""Smoke tests: the package and its public API import."""

import dj_htmx_cbv


def test_package_imports_and_has_version():
    assert dj_htmx_cbv.__version__


def test_public_api_is_exported():
    from dj_htmx_cbv import (
        ContextPersistenceMixin,
        HxResponseMixin,
        HxTemplateView,
        HxTestClient,
        HxView,
        OptimizedQueryMixin,
    )

    assert all(
        [
            HxView,
            HxTemplateView,
            HxResponseMixin,
            ContextPersistenceMixin,
            OptimizedQueryMixin,
            HxTestClient,
        ]
    )
