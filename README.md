# TelegramForwarder 🚀

[![License](https://img.shields.io/github/license/gentlemanhu/TelegramForwarder)](https://github.com/gentlemanhu/TelegramForwarder/blob/main/LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/downloads/)
[![Telegram Bot API](https://img.shields.io/badge/Telegram%20Bot%20API-6.9%2B-blue)](https://core.telegram.org/bots/api)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![GitHub issues](https://img.shields.io/github/issues/gentlemanhu/TelegramForwarder)](https://github.com/gentlemanhu/TelegramForwarder/issues)
[![GitHub stars](https://img.shields.io/github/stars/gentlemanhu/TelegramForwarder)](https://github.com/gentlemanhu/TelegramForwarder/stargazers)
[![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg)](https://github.com/gentlemanhu/TelegramForwarder/blob/main/CONTRIBUTING.md)
[![Activity](https://img.shields.io/github/last-commit/gentlemanhu/TelegramForwarder)](https://github.com/gentlemanhu/TelegramForwarder/commits/main)

TelegramForwarder is a powerful and user-friendly Telegram bot designed for automated message forwarding between channels. Built with Python, it offers an intuitive interface for managing channel content synchronization while supporting all types of media.

[English](#features) | [中文说明](#功能特点)


<div align="center">
  <img src="assets/int.png" alt="Trading Flow" width="100%">
</div>

## ✨ Features

- 🔄 Automated message forwarding between channels
- 📱 User-friendly inline keyboard interface
- 🔍 Monitor multiple source channels
- 📢 Forward to multiple target channels
- 📋 Channel pairing management
- 🖼️ Support for all media types (photos, videos, documents)
- 💾 SQLite database for persistent storage
- 🔒 Owner-only access control
- ⚡ Asynchronous processing for better performance

## 📂 Directory Structure

The project has the following directory structure:

```
TelegramForwarder/
├── data/
│   ├── backups/     # Database backups
│   └── media_cache/ # Temporary media files
├── logs/          # Log files
└── ...
```

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- Telegram Bot Token
- API ID and Hash from Telegram

### Installation

1. Clone the repository:
```bash
git clone https://github.com/gentlemanhu/TelegramForwarder.git
cd TelegramForwarder
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Run the bot:
```bash
python main.py
```

## 🎁 Support the Project

If you find this project helpful, please consider supporting its development:

<div align="center">
  <table>
    <tr>
      <th>Digital Asset</th>
      <th>Address</th>
    </tr>
    <tr>
      <td><img src="https://img.shields.io/badge/Bitcoin-000000?style=flat&logo=bitcoin&logoColor=white"/> BTC</td>
      <td><code>1588hGJGh8WfeQNEydxEcurpPR8CaH9FCX</code></td>
    </tr>
    <tr>
      <td><img src="https://img.shields.io/badge/Tether-50AF95?style=flat&logo=tether&logoColor=white"/> USDT (TRC20)</td>
      <td><code>TY1A9McJd6wz1ZgfVHmLEoQGFJX27WSNoN</code></td>
    </tr>
    <tr>
      <td><img src="https://img.shields.io/badge/Ethereum-3C3C3D?style=flat&logo=ethereum&logoColor=white"/> ETH</td>
      <td><code>0x5aa791a5fe03f823275d7240ebe887d35fdf0f3b</code></td>
    </tr>
  </table>
</div>

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

# 中文说明

## 功能特点

- 🔄 自动转发频道消息
- 📱 友好的内联键盘界面
- 🔍 支持监控多个源频道
- 📢 支持转发到多个目标频道
- 📋 频道配对管理
- 🖼️ 支持所有媒体类型（图片、视频、文档）
- 💾 使用 SQLite 数据库持久化存储
- 🔒 仅限所有者访问控制
- ⚡ 异步处理提升性能

## 📂 目录结构

项目具有以下目录结构：

```
TelegramForwarder/
├── data/
│   ├── backups/     # 数据库备份
│   └── media_cache/ # 临时媒体文件
├── logs/          # 日志文件
└── ...
```

## 快速开始

### 前置要求

- Python 3.8 或更高版本
- Telegram Bot Token
- Telegram API ID 和 Hash

### 安装步骤

1. 克隆仓库：
```bash
git clone https://github.com/gentlemanhu/TelegramForwarder.git
cd TelegramForwarder
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 配置环境变量：
```bash
cp .env.example .env
# 编辑 .env 文件，填入你的配置
```

4. 运行机器人：
```bash
python main.py
```

## 🎁 支持项目

如果您觉得这个项目对您有帮助，欢迎支持项目的开发：

<div align="center">
  <table>
    <tr>
      <th>Digital Asset</th>
      <th>Address</th>
    </tr>
    <tr>
      <td><img src="https://img.shields.io/badge/Bitcoin-000000?style=flat&logo=bitcoin&logoColor=white"/> BTC</td>
      <td><code>1588hGJGh8WfeQNEydxEcurpPR8CaH9FCX</code></td>
    </tr>
    <tr>
      <td><img src="https://img.shields.io/badge/Tether-50AF95?style=flat&logo=tether&logoColor=white"/> USDT (TRC20)</td>
      <td><code>TY1A9McJd6wz1ZgfVHmLEoQGFJX27WSNoN</code></td>
    </tr>
    <tr>
      <td><img src="https://img.shields.io/badge/Ethereum-3C3C3D?style=flat&logo=ethereum&logoColor=white"/> ETH</td>
      <td><code>0x5aa791a5fe03f823275d7240ebe887d35fdf0f3b</code></td>
    </tr>
  </table>
</div>



---

If you find this project helpful, please consider giving it a star ⭐ to show your support!

如果这个项目对你有帮助，请考虑给它一个星标 ⭐ 以示支持！