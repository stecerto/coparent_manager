from django.urls import resolve, Resolver404, reverse
from django.apps import apps

# 🔹 URL → label leggibile
LABEL_MAP = {
    "family_dashboard": "Generale",
    "children_list": "Figli",
    "child_detail": "Figlio",
    "child_edit": "Modifica",
    "child_confirm_delete": "Elimina",
    "expenses_dashboard": "Spese",
    "add_expense": "Aggiungi",
    "edit_expense": "Modifica",
    "chat_home": "Chat",
    "documents_list": "Documenti",
    "calendar_view": "Calendario",
    "summary": "Riepilogo",
    "setup": "Setup",
}

# 🔹 URL → modello per recuperare nome oggetto
MODEL_LABELS = {
    "child_detail": ("children.ChildProfile", "name"),
    "child_edit": ("children.ChildProfile", "name"),
    "child_confirm_delete": ("children.ChildProfile", "name"),
    "edit_expense": ("expenses.Expense", "expense_type"),
}

IGNORE_PARTS = ["families", "accounts", "calendar", "core", "config", ]


def get_object_label(model_path, field, pk):
    try:
        Model = apps.get_model(model_path)
        obj = Model.objects.filter(pk=pk).only(field).first()

        if not obj:
            return str(pk)

        # 👉 supporto choices (es. expense_type)
        display_method = f"get_{field}_display"
        if hasattr(obj, display_method):
            return getattr(obj, display_method)()

        return getattr(obj, field, str(pk))

    except Exception:
        return str(pk)


def breadcrumbs(request):
    crumbs = []

    try:
        path_parts = request.path.strip("/").split("/")
        accumulated = ""

        # 🔹 HOME
        crumbs.append({
            "name": "Home",
            "url": reverse("home")
        })

        for i, part in enumerate(path_parts):
            if not part or part in IGNORE_PARTS:
                continue

            # 🔥 salta numeri puri
            if part.isdigit():
                continue

            accumulated += f"/{part}"

            try:
                match = resolve(accumulated + "/")
                url_name = match.url_name
                kwargs = match.kwargs

                # 🔹 se la view contiene pk/id mostra il nome oggetto
                if ("pk" in kwargs or "id" in kwargs) and url_name in MODEL_LABELS:
                    pk = kwargs.get("pk") or kwargs.get("id")
                    model_path, field = MODEL_LABELS[url_name]

                    label = get_object_label(model_path, field, pk)

                else:
                    label = LABEL_MAP.get(
                        url_name,
                        part.replace("-", " ").replace("_", " ").title()
                    )

                crumbs.append({
                    "name": label,
                    "url": accumulated + "/" if i < len(path_parts) - 1 else None
                })

            except Resolver404:
                crumbs.append({
                    "name": part.replace("-", " ").title(),
                    "url": None
                })

    except Exception:
        pass

    return {"breadcrumbs": crumbs}