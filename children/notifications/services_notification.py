def notify_other_parent(child, message, sender):

    family = child.family

    other_users = family.members.exclude(user=sender)

    for member in other_users:
        # per ora semplice log (poi puoi fare email / whatsapp)
        print(f"NOTIFICA a {member.user.email}: {message}")