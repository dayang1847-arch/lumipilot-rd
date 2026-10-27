# LumiPilot-R&D

电子研发方案台：客户需求 → 方案对比 → 选择理由 → 待确认事项。

保留已选第二版对比界面、客户/销售/工程师阅读视角、历史案例、沟通清单下载与完整工程知识网络。所有业务页面、JSON和附件请求均由服务器验证登录。

## 仓库与运行边界

- 代码仓库可公开；真实研发案例、报告、原件和账号配置均单独保存在运行数据卷。显示名称为 LumiPilot-R&D；当前GitHub路径为 dayang1847-arch/lumipilot-rd。
- GitHub只保存应用代码、界面和部署说明；真实案例、整理后的知识库、分析报告、原始原理图、BOM和测试文件均不在仓库中。
- GitHub Pages是静态托管，不能直接运行本项目的服务器登录。上线需支持Python或Docker的服务器；本仓库不发布无保护的Pages站点。
- 运行凭据和会话保存在仓库外的数据目录。没有凭据配置时，服务启动失败，不提供匿名回退。

## 本机启动

Python 3.10及以上，无第三方运行依赖。

```sh
python scripts/setup_admin.py --username admin
python server.py --local
```

打开 http://127.0.0.1:8988 。初始化命令交互读取密码，保存PBKDF2校验摘要，不接受命令行密码参数。`.runtime/`不得提交。账号密码由管理员在目标运行环境初始化。

若需要读取原始文件，在启动前设置 `RD_SOURCES_DIR` 指向“资料快照”内容的根目录；保留原有相对路径。未安装原始文件时，相关链接登录后会提示尚未导入。

## HTTPS服务器部署

1. 安装Docker和Compose，克隆本仓库。
2. 为服务器准备域名及DNS。复制 `.env.example` 为 `.env`，填写 `RD_DOMAIN`，例如 `rd.example.com`。
3. 创建运行数据目录并赋给容器用户；源资料目录只读挂载：

```sh
mkdir -p runtime source-data
sudo chown 10001:10001 runtime
sudo chmod 700 runtime
```

4. 初始化账号，交互输入所需密码：

```sh
docker compose build
docker compose run --rm app python scripts/setup_admin.py --username admin --file /var/lib/lumipilot-rd/auth.json
```

5. 将私有案例包中的 `private-web/` 放入 `runtime/private-web/`，确保容器用户可读。知识库和案例由服务器在登录后注入页面。未导入时界面明确显示资料缺口。原始文件另外通过私有通道复制到 `source-data/`，不提交GitHub。
6. 启动：

```sh
docker compose up -d
docker compose ps
```

Caddy负责HTTPS。只有80/443公开，应用8988端口不发布到宿主机。生产模式要求 `RD_PUBLIC_ORIGIN` 为HTTPS域名。Host/Origin校验与生产域名一致。

新环境验收应包含：登录、直接访问知识库JSON与源文件的登录限制、清单下载、退出、TLS、数据卷权限与备份恢复。Docker/Linux、DNS和TLS必须在目标服务器另行验证；本机单元测试不能替代线上验收。

## 凭据与会话

- 用户名由初始化配置决定，默认admin。
- 密码使用随机盐和PBKDF2-SHA256（600000轮）保存摘要，不进入前端文件或仓库。
- 会话使用32字节随机令牌；服务器只保存令牌摘要，8小时失效。
- Cookie为HttpOnly、SameSite=Strict；HTTPS下使用Secure和`__Host-`前缀。
- 登录和退出要求同源请求；退出还要求会话CSRF令牌并撤销服务端会话。
- 失败登录限流，私有响应禁止缓存。原始文件和JSON不能绕过首页直接匿名访问。
- 健康检查只返回应用状态，不返回研发数据。日志不记录表单、Cookie或源资料路径。

## 更新界面或案例

原本地资料库继续独立维护。本项目的复制脚本只读取它，不修改原件：

```sh
python scripts/pack_app.py --from '/absolute/path/to/approved-local-delivery'
python scripts/verify_release.py
python -m unittest discover -s tests -v
```

复制脚本将真实案例、JSON和报告移至忽略的 `.runtime/private-web/`，只在 `web/` 生成不含真实研发载荷的代码；同时移除私有数据中的本机绝对路径，将旧工程页脚本提取为外部资源，以适配登录服务的内容安全策略。它不复制原始研发文件或运行凭据。GitHub Actions执行认证边界与发布内容检查。

## 资料状态

历史案例用于参考，不能自动认定当前客户适用、物料可替代或工程已批准。未提供可比采购实价时，不计算节省金额。详见登录后的使用说明与分析报告。
