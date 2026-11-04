from django.apps import apps as global_apps
from django.contrib.auth import management as auth_management
from django.contrib.contenttypes.management import create_contenttypes
from django.db import DEFAULT_DB_ALIAS, router


# MongoDB compatibility fix for Django's post-migrate permission creation.
# The stock code hashes ContentType model instances directly, which fails when
# ObjectId-backed objects do not yet have a saved primary key during setup.
def _mongo_safe_create_permissions(
    app_config,
    verbosity=2,
    interactive=True,
    using=DEFAULT_DB_ALIAS,
    apps=global_apps,
    **kwargs,
):
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
    ctypes = ContentType.objects.db_manager(using).get_for_models(
        *models,
        for_concrete_models=False,
    )

    content_type_ids = [
        ct.pk for ct in ctypes.values() if getattr(ct, "pk", None) is not None
    ]
    if not content_type_ids:
        return

    all_perms = set(
        Permission.objects.using(using)
        .filter(content_type__in=content_type_ids)
        .values_list("content_type", "codename")
    )

    perms = []
    for model in models:
        ctype = ctypes[model]
        for codename, name in auth_management._get_builtin_permissions(model._meta):
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


auth_management.create_permissions = _mongo_safe_create_permissions
