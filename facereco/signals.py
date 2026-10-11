
from django.db.models.signals import pre_delete, post_delete
from django.dispatch import receiver

from .models import Register, ParentStudentLink, ParentProfile


@receiver(pre_delete, sender=Register)
def remember_student_parents(sender, instance, **kwargs):
    # Student delete hone se pehle linked parents ki IDs save karo.
    instance._parent_ids_to_check = list(
        ParentStudentLink.objects.filter(
            student=instance
        ).values_list("parent_id", flat=True)
    )


@receiver(post_delete, sender=Register)
def delete_orphaned_parent_accounts(sender, instance, **kwargs):
    # Student delete hone ke baad parents ke remaining children check karo.
    parent_ids = getattr(instance, "_parent_ids_to_check", [])

    for parent_id in parent_ids:
        # Agar parent ke aur bachche linked hain, account rehne do.
        if ParentStudentLink.objects.filter(parent_id=parent_id).exists():
            continue

        parent = ParentProfile.objects.filter(pk=parent_id).select_related(
            "user"
        ).first()

        if parent:
            # Parent ka account aur usse linked profile delete karo.
            parent.user.delete()
