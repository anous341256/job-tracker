# Job Tracker 数据模型设计

状态：已确认的初始设计基线。实现模型和迁移时以本文档为准；如果设计变化，应先更新本文档。

## 设计原则

- 所有私人业务数据必须属于用户，并在查询层做用户隔离。
- 公司状态、职位状态、投递状态分别建模，不复用同一个状态概念。
- 公司官网和招聘官网分别保存；投递截止日期属于职位，不属于公司。
- 重要状态变化保留历史，不只保存当前值。
- 主要业务表统一包含 `created_at`、`updated_at`；需要保留历史的数据优先归档而非直接删除。
- 密码和数据库凭据只从环境变量读取，不进入 Git。

## 实施顺序

1. `accounts.User` 自定义用户模型（继承 `AbstractUser`）
2. `Company`
3. `JobPosition`
4. `Application`
5. `ApplicationStatusLog`
6. `Interview`
7. 第二阶段再实现 `Contact`、`Resume`、`Document`、`Communication`、`Tag`

## 核心实体

### User

- 第一版继承 Django `AbstractUser`，尽量不增加业务字段。
- 在首次正式迁移前配置 `AUTH_USER_MODEL`。
- 个人求职资料等可变业务信息以后放入独立 Profile，而不是持续堆进用户表。

### Company

- 归属：`user`
- 核心字段：`name`、`status`、`website_url`、`careers_url`、`industry`、`location`、`company_size`、`priority`、`notes`、`archived_at`
- 状态：`researching`、`watching`、`target`、`active`、`paused`、`rejected`、`archived`
- 优先级：`low`、`medium`、`high`、`dream`
- 约束：同一用户下公司名称唯一。

### JobPosition

- 归属：`company`
- 核心字段：`title`、`department`、`status`、`description`、`source_url`、`application_deadline`、`published_at`、`location`、`work_mode`、`employment_type`、薪资结构字段、`requirements`、`benefits`、`notes`
- 状态：`draft`、`open`、`closed`、`expired`、`filled`、`unknown`
- 办公方式：`onsite`、`hybrid`、`remote`、`unknown`
- 薪资拆为 `salary_min`、`salary_max`、`salary_currency`、`salary_period`，不保存为单一展示字符串。
- 同公司同名职位不强制唯一；以后使用公司、标题和来源链接做重复提醒。

### Application

- 归属：`user`；关联 `job_position`
- 核心字段：`status`、`applied_at`、`source`、`source_detail`、`priority`、`next_action`、`next_action_date`、`last_contact_at`、`expected_salary`、`notes`、`withdrawn_reason`、`rejection_reason`
- 状态：`preparing`、`applied`、`screening`、`assessment`、`interviewing`、`offer`、`accepted`、`rejected`、`withdrawn`、`ghosted`、`closed`
- 来源：`company_website`、`job_board`、`referral`、`recruiter`、`campus`、`social_media`、`other`
- 一个职位允许存在历史上的多次投递，但同一时间只能有一条有效投递。

### ApplicationStatusLog

- 归属：`application`
- 字段：`from_status`、`to_status`、`changed_at`、`note`、`changed_by`
- 用于投递时间线、各阶段耗时及转化统计。

### Interview

- 归属：`application`
- 字段：`round_number`、`title`、`interview_type`、`status`、`scheduled_at`、`duration_minutes`、`meeting_url`、`location`、`interviewer_names`、`preparation_notes`、`questions`、`reflection`、`result`
- 类型：`phone`、`video`、`onsite`、`technical`、`behavioral`、`hr`、`case_study`、`other`
- 状态：`scheduled`、`completed`、`cancelled`、`rescheduled`、`no_show`
- 结果：`pending`、`passed`、`failed`、`unknown`

## 第二阶段实体

- `Contact`：HR、猎头、内推人、面试官及最近联系时间。
- `Resume`：简历版本，并记录每次投递使用的版本。
- `Document`：简历、求职信、Offer、JD 截图等附件。
- `Communication`：邮件、电话、微信、LinkedIn 等沟通记录。
- `Tag`：公司、职位和投递的用户自定义标签。

## 删除与归档

- 有职位或投递关联的公司优先归档，不直接删除。
- 已产生投递的职位应阻止直接删除。
- 删除投递时，状态历史和面试记录可随之级联删除。
- 用户删除时，其私人业务数据随之删除；执行前必须提供明确确认和数据导出提示。

