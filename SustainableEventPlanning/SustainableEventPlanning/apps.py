from bson import ObjectId
from django.apps import apps as global_apps
from django.contrib import auth
from django.contrib.admin.apps import AdminConfig
from django.contrib.auth.apps import AuthConfig
from django.contrib.contenttypes.apps import ContentTypesConfig
from django.contrib.contenttypes.management import create_contenttypes
from django.core import exceptions
from django.core.management.color import color_style
from django.db import DEFAULT_DB_ALIAS, router


MONGODB_AUTO_FIELD = "django_mongodb_backend.fields.ObjectIdAutoField"

try:
    from django_mongodb_backend.fields import ObjectIdAutoField
except ImportError:  # pragma: no cover
    ObjectIdAutoField = None


if ObjectIdAutoField is not None and not getattr(ObjectIdAutoField, "_sustainable_patch", False):
    def _get_pk_value_on_save(self, instance):
        value = getattr(instance, self.attname, None)
        if value is None or value == "":
            value = ObjectId()
            setattr(instance, self.attname, value)
        return value

    ObjectIdAutoField.get_pk_value_on_save = _get_pk_value_on_save
    ObjectIdAutoField._sustainable_patch = True


def _mongo_safe_create_permissions(app_config, verbosity=2, interactive=True, using=DEFAULT_DB_ALIAS, apps=global_apps, **kwargs):
    if not app_config.models_module:
        return

    try:
        Permission = apps.get_model("auth", "Permission")
    except LookupError:
        return
    if not router.allow_migrate_model(using, Permission):
        return

    create_contenttypes(
        app_config,
        verbosity=verbosity,
        interactive=interactive,
        using=using,
        apps=apps,
        **kwargs,
    )

    app_label = app_config.label
    try:
        app_config = apps.get_app_config(app_label)
        ContentType = apps.get_model("contenttypes", "ContentType")
    except LookupError:
        return

    models = list(app_config.get_models())
    ctypes = ContentType.objects.db_manager(using).get_for_models(*models, for_concrete_models=False)
    content_type_ids = [ct.pk for ct in ctypes.values() if getattr(ct, 'pk', None) is not None]

    all_perms = set()
    if content_type_ids:
        all_perms = set(
            Permission.objects.using(using)
            .filter(content_type__in=content_type_ids)
            .values_list("content_type", "codename")
        )

    perms = []
    for model in models:
        ctype = ctypes[model]
        for codename, name in auth.management._get_builtin_permissions(model._meta):
            if (ctype.pk, codename) not in all_perms:
                permission = Permission()
                permission._state.db = using
                permission.codename = codename
                permission.name = name
                permission.content_type = ctype
                perms.append(permission)

    Permission.objects.using(using).bulk_create(perms)
    if verbosity >= 2:
        for perm in perms:
            print("Adding permission '%s'" % perm)


auth.management.create_permissions = _mongo_safe_create_permissions


class MongoDBAdminConfig(AdminConfig):
    default_auto_field = MONGODB_AUTO_FIELD


class MongoDBAuthConfig(AuthConfig):
    default_auto_field = MONGODB_AUTO_FIELD


class MongoDBContentTypesConfig(ContentTypesConfig):
    default_auto_field = MONGODB_AUTO_FIELD