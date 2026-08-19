import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0005_action_center_relations'),
        ('mailboxes', '0004_emailaccount_sync_folder_syncedemail_folder_name_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='todoitem',
            name='source_email',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='todo_items', to='mailboxes.syncedemail', verbose_name='来源邮件'),
        ),
        migrations.AddField(
            model_name='todoitem',
            name='source_url',
            field=models.URLField(blank=True, max_length=1000, verbose_name='操作链接'),
        ),
    ]
