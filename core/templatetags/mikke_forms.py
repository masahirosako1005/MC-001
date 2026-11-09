"""フォーム部品のアクセシビリティ補助。

{% described field %} で入力欄を出すと、補足説明 (help) とエラーの id を aria-describedby に入れ、
エラーがあれば aria-invalid="true" を付ける (スクリーンリーダーが補足文・エラーを読み上げられるように)。
"""

from django import template

register = template.Library()


@register.simple_tag
def described(field):
    ids = []
    if field.help_text:
        ids.append(f"{field.auto_id}_help")
    if field.errors:
        ids.append(f"{field.auto_id}_errors")
    attrs = {}
    if ids:
        existing = field.field.widget.attrs.get("aria-describedby")
        attrs["aria-describedby"] = " ".join(([existing] if existing else []) + ids)
    if field.errors:
        attrs["aria-invalid"] = "true"
    return field.as_widget(attrs=attrs)
