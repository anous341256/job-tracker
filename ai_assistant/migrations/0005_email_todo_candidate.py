import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('ai_assistant', '0004_email_assistant_workbench'),
        ('applications', '0003_application_resume'),
        ('companies', '0004_company_pinned_order'),
        ('mailboxes', '0004_emailaccount_sync_folder_syncedemail_folder_name_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='emailassistantthread',
            name='resolution',
            field=models.CharField(blank=True, choices=[('with_schedule', '发现行动事项并已处理'), ('no_schedule', '确认没有行动事项')], max_length=20),
        ),
        migrations.CreateModel(
            name='EmailTodoCandidate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('version', models.PositiveIntegerField(default=1)),
                ('status', models.CharField(choices=[('pending', '待审核'), ('needs_info', '需要补充'), ('approved', '已创建 To Do'), ('rejected', '已忽略'), ('superseded', '已被新建议替代')], default='pending', max_length=20)),
                ('title', models.CharField(max_length=200)),
                ('action_type', models.CharField(choices=[('resume_submit', '提交简历'), ('document_submit', '提交材料'), ('assessment', '完成适性检查/笔试'), ('form_fill', '填写表单'), ('email_reply', '回复邮件'), ('schedule_booking', '预约时间'), ('follow_up', '跟进'), ('other', '其他')], default='other', max_length=30)),
                ('due_at', models.DateTimeField(blank=True, null=True)),
                ('timezone_name', models.CharField(default='Asia/Tokyo', max_length=64)),
                ('priority', models.CharField(choices=[('low', '低'), ('medium', '中'), ('high', '高')], default='medium', max_length=10)),
                ('action_url', models.URLField(blank=True, max_length=1000)),
                ('notes', models.TextField(blank=True)),
                ('evidence', models.TextField(blank=True)),
                ('missing_fields', models.JSONField(blank=True, default=list)),
                ('confidence', models.FloatField(default=0)),
                ('created_object_id', models.PositiveBigIntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('application', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='email_todo_candidates', to='applications.application')),
                ('company', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='email_todo_candidates', to='companies.company')),
                ('email', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='todo_candidates', to='mailboxes.syncedemail')),
                ('job_position', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='email_todo_candidates', to='companies.jobposition')),
                ('source_message', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='todo_candidates', to='ai_assistant.emailassistantmessage')),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='todo_candidates', to='ai_assistant.aitask')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='email_todo_candidates', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('-created_at',)},
        ),
        migrations.AddIndex(
            model_name='emailtodocandidate',
            index=models.Index(fields=['user', 'status', 'due_at'], name='email_todo_review_idx'),
        ),
    ]
