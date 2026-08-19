from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('mailboxes', '0002_initial')]

    operations = [
        migrations.AlterField(
            model_name='emailaccount',
            name='provider',
            field=models.CharField(
                choices=[
                    ('gmail', 'Gmail'),
                    ('outlook', 'Outlook'),
                    ('outlook_local', '本机 Outlook（只读）'),
                ],
                max_length=20,
            ),
        ),
    ]
