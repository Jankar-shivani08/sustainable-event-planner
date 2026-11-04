from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User

from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    extra = 0
    max_num = 1
    fields = ('role', 'organization', 'phone', 'bio')


class UserAdmin(DjangoUserAdmin):
    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'profile_role',
        'profile_organization',
        'is_staff',
        'is_active',
    )
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'profile__role')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'profile__organization')
    ordering = ('username',)
    list_select_related = ('profile',)
    inlines = (UserProfileInline,)
    list_per_page = 50

    @admin.display(description='Role', ordering='profile__role')
    def profile_role(self, obj):
        return obj.profile.role

    @admin.display(description='Organization', ordering='profile__organization')
    def profile_organization(self, obj):
        return obj.profile.organization


if admin.site.is_registered(User):
    admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'organization', 'phone', 'created_at')
    list_filter = ('role', 'created_at')
    search_fields = ('user__username', 'user__email', 'organization', 'phone')
    ordering = ('-created_at',)
    list_select_related = ('user',)
    list_per_page = 50
