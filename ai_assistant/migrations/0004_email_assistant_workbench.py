import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('ai_assistant', '0003_alter_aitask_status'),
        ('mailboxes', '0004_emailaccount_sync_folder_syncedemail_folder_name_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailAssistantThread',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', '待检查'), ('in_review', '检查中'), ('reviewed', '已完成')], default='pending', max_length=20)),
                ('resolution', models.CharField(blank=True, choices=[('with_schedule', '发现日程并已处理'), ('no_schedule', '确认没有日程')], max_length=20)),
                ('last_activity_at', models.DateTimeField(auto_now=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('email', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='assistant_thread', to='mailboxes.syncedemail')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='email_assistant_threads', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('-last_activity_at',)},
        ),
        migrations.AddIndex(model_name='emailassistantthread', index=models.Index(fields=['user', 'status', 'last_activity_at'], name='email_asst_review_idx')),
        migrations.AddField(model_name='aitask', name='email_thread', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='ai_tasks', to='ai_assistant.emailassistantthread')),
        migrations.AlterField(model_name='aitask', name='task_type', field=models.CharField(choices=[('jd_parse', 'JD 结构化解析'), ('job_match', '简历职位匹配'), ('email_schedule', '邮件日程提取'), ('email_chat', '邮件助手对话')], max_length=20)),
        migrations.CreateModel(
            name='EmailAssistantMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('user', '用户'), ('assistant', '千问')], max_length=20)),
                ('content', models.TextField()),
                ('client_request_id', models.UUIDField(blank=True, null=True, unique=True)),
                ('structured_data', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('task', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assistant_messages', to='ai_assistant.aitask')),
                ('thread', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='ai_assistant.emailassistantthread')),
            ],
            options={'ordering': ('created_at', 'pk')},
        ),
        migrations.AddIndex(model_name='emailassistantmessage', index=models.Index(fields=['thread', 'created_at'], name='email_asst_msg_idx')),
        migrations.AddField(model_name='emailschedulecandidate', name='source_message', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='schedule_candidates', to='ai_assistant.emailassistantmessage')),
        migrations.AddField(model_name='emailschedulecandidate', name='version', field=models.PositiveIntegerField(default=1)),
        migrations.AlterField(model_name='emailschedulecandidate', name='status', field=models.CharField(choices=[('pending', '待审核'), ('needs_info', '需要补充'), ('approved', '已加入日程'), ('rejected', '已忽略'), ('superseded', '已被新建议替代')], default='pending', max_length=20)),
    ]
