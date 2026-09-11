from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Contact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("first", models.CharField(blank=True, max_length=100)),
                ("last", models.CharField(blank=True, max_length=100)),
                ("phone", models.CharField(blank=True, max_length=50)),
                ("email", models.CharField(blank=True, max_length=254)),
            ],
            options={"ordering": ["id"]},
        ),
    ]
