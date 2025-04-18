# database.py
import sqlite3
from typing import List, Dict, Optional, Any
import logging
from datetime import datetime

class Database:
    def __init__(self, db_name: str):
        self.database_name = db_name
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.setup_database()

    def setup_database(self):
        """初始化数据库表"""
        # 首先检查数据库是否已存在且有数据
        import os
        import time
        import shutil

        existing_db = os.path.exists(self.database_name) and os.path.getsize(self.database_name) > 0

        # 如果数据库已存在，创建备份
        if existing_db:
            # 确保备份目录存在
            backup_dir = "data/backups"
            os.makedirs(backup_dir, exist_ok=True)

            # 生成备份文件名
            db_filename = os.path.basename(self.database_name)
            backup_name = os.path.join(backup_dir, f"{db_filename}.backup_{int(time.time())}")

            # 创建备份
            shutil.copy2(self.database_name, backup_name)
            logging.info(f"已创建数据库备份: {backup_name}")

        # 使用 CREATE TABLE IF NOT EXISTS 添加新表
        # 这样不会影响现有表和数据
        self.cursor.executescript('''
            CREATE TABLE IF NOT EXISTS channels (
                channel_id INTEGER PRIMARY KEY,
                channel_name TEXT,
                channel_username TEXT,
                channel_type TEXT CHECK(channel_type IN ('MONITOR', 'FORWARD')),
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS channel_pairs (
                monitor_channel_id INTEGER,
                forward_channel_id INTEGER,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                PRIMARY KEY (monitor_channel_id, forward_channel_id),
                FOREIGN KEY (monitor_channel_id) REFERENCES channels(channel_id),
                FOREIGN KEY (forward_channel_id) REFERENCES channels(channel_id)
            );

            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                language TEXT DEFAULT 'en',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- 新增过滤规则表
            CREATE TABLE IF NOT EXISTS filter_rules (
                rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair_id TEXT,  -- 格式："monitor_id:forward_id"
                rule_type TEXT CHECK(rule_type IN ('WHITELIST', 'BLACKLIST')),
                filter_mode TEXT CHECK(filter_mode IN ('KEYWORD', 'REGEX')),
                pattern TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- 新增时间段设置表
            CREATE TABLE IF NOT EXISTS time_filters (
                filter_id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair_id TEXT,  -- 格式："monitor_id:forward_id"
                start_time TEXT,  -- 格式："HH:MM"
                end_time TEXT,    -- 格式："HH:MM"
                days_of_week TEXT,  -- 格式："1,2,3,4,5,6,7" （1=周一）
                is_active BOOLEAN DEFAULT 1,
                mode TEXT CHECK(mode IN ('ALLOW', 'BLOCK')) DEFAULT 'ALLOW',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- 新增消息转发关系跟踪表
            CREATE TABLE IF NOT EXISTS forwarded_messages (
                original_chat_id INTEGER,
                original_message_id INTEGER,
                forwarded_chat_id INTEGER,
                forwarded_message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (original_chat_id, original_message_id, forwarded_chat_id)
            );

            CREATE INDEX IF NOT EXISTS idx_channels_type
            ON channels(channel_type);

            CREATE INDEX IF NOT EXISTS idx_channels_active
            ON channels(is_active);

            CREATE INDEX IF NOT EXISTS idx_pairs_monitor
            ON channel_pairs(monitor_channel_id);

            CREATE INDEX IF NOT EXISTS idx_pairs_forward
            ON channel_pairs(forward_channel_id);

            CREATE INDEX IF NOT EXISTS idx_pairs_active
            ON channel_pairs(is_active);

            -- 新增索引
            CREATE INDEX IF NOT EXISTS idx_filter_rules_pair_id
            ON filter_rules(pair_id);

            CREATE INDEX IF NOT EXISTS idx_filter_rules_active
            ON filter_rules(is_active);

            CREATE INDEX IF NOT EXISTS idx_time_filters_pair_id
            ON time_filters(pair_id);

            CREATE INDEX IF NOT EXISTS idx_time_filters_active
            ON time_filters(is_active);
        ''')
        self.conn.commit()

    def get_user_language(self, user_id: int) -> str:
        """获取用户语言设置"""
        try:
            self.cursor.execute('''
                SELECT language FROM user_preferences
                WHERE user_id = ?
            ''', (user_id,))
            result = self.cursor.fetchone()
            return result[0] if result else 'en'
        except sqlite3.Error as e:
            logging.error(f"Error getting user language: {e}")
            return 'en'

    def set_user_language(self, user_id: int, language: str) -> bool:
        """设置用户语言偏好"""
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO user_preferences (user_id, language, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, language))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"Error setting user language: {e}")
            return False

    def add_channel(self, channel_id: int, channel_name: str,
                   channel_username: Optional[str], channel_type: str) -> bool:
        """添加新频道"""
        try:
            # 首先检查频道是否已存在
            self.cursor.execute('''
                SELECT channel_id, is_active FROM channels
                WHERE channel_id = ?
            ''', (channel_id,))
            existing = self.cursor.fetchone()

            if existing:
                # 如果频道存在但被停用，重新激活它
                if not existing[1]:
                    self.cursor.execute('''
                        UPDATE channels
                        SET is_active = 1,
                            channel_name = ?,
                            channel_username = ?,
                            channel_type = ?,
                            added_date = CURRENT_TIMESTAMP
                        WHERE channel_id = ?
                    ''', (channel_name, channel_username, channel_type, channel_id))
                else:
                    # 更新现有频道信息
                    self.cursor.execute('''
                        UPDATE channels
                        SET channel_name = ?,
                            channel_username = ?,
                            channel_type = ?
                        WHERE channel_id = ?
                    ''', (channel_name, channel_username, channel_type, channel_id))
            else:
                # 添加新频道
                self.cursor.execute('''
                    INSERT INTO channels
                    (channel_id, channel_name, channel_username, channel_type)
                    VALUES (?, ?, ?, ?)
                ''', (channel_id, channel_name, channel_username, channel_type))

            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"Error in add_channel: {e}")
            return False

    def remove_channel(self, channel_id: int) -> bool:
        """移除频道"""
        try:
            # 开始事务
            self.cursor.execute('BEGIN TRANSACTION')

            # 停用所有涉及该频道的配对
            self.cursor.execute('''
                UPDATE channel_pairs
                SET is_active = 0
                WHERE monitor_channel_id = ? OR forward_channel_id = ?
            ''', (channel_id, channel_id))

            # 停用频道
            self.cursor.execute('''
                UPDATE channels
                SET is_active = 0
                WHERE channel_id = ?
            ''', (channel_id,))

            # 提交事务
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            # 发生错误时回滚
            self.conn.rollback()
            logging.error(f"Error in remove_channel: {e}")
            return False

    def get_channels_by_type(self, channel_type: str, page: int = 1, per_page: int = 7) -> Dict[str, Any]:
        """分页获取指定类型的频道"""
        try:
            # 获取总数
            self.cursor.execute('''
                SELECT COUNT(*) FROM channels
                WHERE channel_type = ? AND is_active = 1
            ''', (channel_type,))
            total = self.cursor.fetchone()[0]

            # 计算总页数
            total_pages = (total + per_page - 1) // per_page if total > 0 else 1

            # 确保页码有效
            page = max(1, min(page, total_pages))

            # 计算偏移量
            offset = (page - 1) * per_page

            # 获取当前页的数据
            self.cursor.execute('''
                SELECT channel_id, channel_name, channel_username, is_active
                FROM channels
                WHERE channel_type = ? AND is_active = 1
                ORDER BY added_date DESC
                LIMIT ? OFFSET ?
            ''', (channel_type, per_page, offset))

            channels = [{
                'channel_id': row[0],
                'channel_name': row[1],
                'channel_username': row[2],
                'is_active': row[3]
            } for row in self.cursor.fetchall()]

            return {
                'channels': channels,
                'total': total,
                'current_page': page,
                'total_pages': total_pages,
                'per_page': per_page
            }
        except sqlite3.Error as e:
            logging.error(f"Error in get_channels_by_type: {e}")
            return {
                'channels': [],
                'total': 0,
                'current_page': 1,
                'total_pages': 1,
                'per_page': per_page
            }

    def get_channel_pairs(self, page: int = 1, per_page: int = 7) -> Dict[str, Any]:
        """分页获取所有活跃的频道配对"""
        try:
            # 获取总数
            self.cursor.execute('''
                SELECT COUNT(*)
                FROM channel_pairs cp
                JOIN channels m ON cp.monitor_channel_id = m.channel_id
                JOIN channels f ON cp.forward_channel_id = f.channel_id
                WHERE cp.is_active = 1
                AND m.is_active = 1
                AND f.is_active = 1
            ''')
            total = self.cursor.fetchone()[0]

            # 计算总页数
            total_pages = (total + per_page - 1) // per_page if total > 0 else 1

            # 确保页码有效
            page = max(1, min(page, total_pages))

            # 计算偏移量
            offset = (page - 1) * per_page

            # 获取当前页的数据
            self.cursor.execute('''
                SELECT
                    cp.monitor_channel_id,
                    cp.forward_channel_id,
                    m.channel_name as monitor_name,
                    f.channel_name as forward_name,
                    cp.added_date
                FROM channel_pairs cp
                JOIN channels m ON cp.monitor_channel_id = m.channel_id
                JOIN channels f ON cp.forward_channel_id = f.channel_id
                WHERE cp.is_active = 1
                AND m.is_active = 1
                AND f.is_active = 1
                ORDER BY cp.added_date DESC
                LIMIT ? OFFSET ?
            ''', (per_page, offset))

            pairs = [{
                'monitor_channel_id': row[0],
                'forward_channel_id': row[1],
                'monitor_name': row[2],
                'forward_name': row[3],
                'added_date': row[4]
            } for row in self.cursor.fetchall()]

            return {
                'pairs': pairs,
                'total': total,
                'current_page': page,
                'total_pages': total_pages,
                'per_page': per_page
            }
        except sqlite3.Error as e:
            logging.error(f"Error in get_channel_pairs: {e}")
            return {
                'pairs': [],
                'total': 0,
                'current_page': 1,
                'total_pages': 1,
                'per_page': per_page
            }

    def get_unpaired_forward_channels(self, monitor_channel_id: int,
                                    page: int = 1, per_page: int = 7) -> Dict[str, Any]:
        """获取未与指定监控频道配对的转发频道（带分页）"""
        try:
            # 获取总数
            self.cursor.execute('''
                SELECT COUNT(*)
                FROM channels c
                WHERE c.channel_type = 'FORWARD'
                AND c.is_active = 1
                AND c.channel_id NOT IN (
                    SELECT forward_channel_id
                    FROM channel_pairs
                    WHERE monitor_channel_id = ?
                    AND is_active = 1
                )
            ''', (monitor_channel_id,))
            total = self.cursor.fetchone()[0]

            # 计算总页数
            total_pages = (total + per_page - 1) // per_page if total > 0 else 1

            # 确保页码有效
            page = max(1, min(page, total_pages))

            # 计算偏移量
            offset = (page - 1) * per_page

            # 获取数据
            self.cursor.execute('''
                SELECT c.channel_id, c.channel_name, c.channel_username
                FROM channels c
                WHERE c.channel_type = 'FORWARD'
                AND c.is_active = 1
                AND c.channel_id NOT IN (
                    SELECT forward_channel_id
                    FROM channel_pairs
                    WHERE monitor_channel_id = ?
                    AND is_active = 1
                )
                ORDER BY c.added_date DESC
                LIMIT ? OFFSET ?
            ''', (monitor_channel_id, per_page, offset))

            channels = [{
                'channel_id': row[0],
                'channel_name': row[1],
                'channel_username': row[2]
            } for row in self.cursor.fetchall()]

            return {
                'channels': channels,
                'total': total,
                'current_page': page,
                'total_pages': total_pages,
                'per_page': per_page
            }
        except sqlite3.Error as e:
            logging.error(f"Error in get_unpaired_forward_channels: {e}")
            return {
                'channels': [],
                'total': 0,
                'current_page': 1,
                'total_pages': 1,
                'per_page': per_page
            }

    def get_forward_channels(self, monitor_channel_id: int,
                           page: int = 1, per_page: int = 7) -> Dict[str, Any]:
        """获取监控频道对应的所有转发频道（带分页）"""
        try:
            # 获取总数
            self.cursor.execute('''
                SELECT COUNT(*)
                FROM channels c
                JOIN channel_pairs cp ON c.channel_id = cp.forward_channel_id
                WHERE cp.monitor_channel_id = ?
                AND cp.is_active = 1
                AND c.is_active = 1
            ''', (monitor_channel_id,))
            total = self.cursor.fetchone()[0]

            # 计算总页数
            total_pages = (total + per_page - 1) // per_page if total > 0 else 1

            # 确保页码有效
            page = max(1, min(page, total_pages))

            # 计算偏移量
            offset = (page - 1) * per_page

            # 获取数据
            self.cursor.execute('''
                SELECT
                    c.channel_id,
                    c.channel_name,
                    c.channel_username,
                    cp.added_date
                FROM channels c
                JOIN channel_pairs cp ON c.channel_id = cp.forward_channel_id
                WHERE cp.monitor_channel_id = ?
                AND cp.is_active = 1
                AND c.is_active = 1
                ORDER BY cp.added_date DESC
                LIMIT ? OFFSET ?
            ''', (monitor_channel_id, per_page, offset))

            channels = [{
                'channel_id': row[0],
                'channel_name': row[1],
                'channel_username': row[2],
                'added_date': row[3]
            } for row in self.cursor.fetchall()]

            return {
                'channels': channels,
                'total': total,
                'current_page': page,
                'total_pages': total_pages,
                'per_page': per_page
            }
        except sqlite3.Error as e:
            logging.error(f"Error in get_forward_channels: {e}")
            return {
                'channels': [],
                'total': 0,
                'current_page': 1,
                'total_pages': 1,
                'per_page': per_page
            }

    def get_all_forward_channels(self, monitor_channel_id: int) -> List[Dict[str, Any]]:
            """获取监控频道对应的所有活跃转发频道（不分页，用于消息转发）"""
            try:
                self.cursor.execute('''
                    SELECT
                        c.channel_id,
                        c.channel_name,
                        c.channel_username,
                        cp.added_date
                    FROM channels c
                    JOIN channel_pairs cp ON c.channel_id = cp.forward_channel_id
                    WHERE cp.monitor_channel_id = ?
                    AND cp.is_active = 1
                    AND c.is_active = 1
                    ORDER BY cp.added_date ASC
                ''', (monitor_channel_id,))

                return [{
                    'channel_id': row[0],
                    'channel_name': row[1],
                    'channel_username': row[2],
                    'added_date': row[3]
                } for row in self.cursor.fetchall()]

            except sqlite3.Error as e:
                logging.error(f"Error in get_all_forward_channels: {e}")
                return []

    def add_channel_pair(self, monitor_channel_id: int, forward_channel_id: int) -> bool:
        """添加频道配对"""
        try:
            # 开始事务
            self.cursor.execute('BEGIN TRANSACTION')

            # 验证两个频道都存在且活跃
            self.cursor.execute('''
                SELECT COUNT(*) FROM channels
                WHERE channel_id IN (?, ?)
                AND is_active = 1
            ''', (monitor_channel_id, forward_channel_id))

            if self.cursor.fetchone()[0] != 2:
                raise sqlite3.Error("One or both channels are not active")

            # 检查配对是否已存在
            self.cursor.execute('''
                SELECT is_active
                FROM channel_pairs
                WHERE monitor_channel_id = ?
                AND forward_channel_id = ?
            ''', (monitor_channel_id, forward_channel_id))

            existing_pair = self.cursor.fetchone()

            if existing_pair:
                if not existing_pair[0]:
                    # 如果配对存在但未激活，重新激活它
                    self.cursor.execute('''
                        UPDATE channel_pairs
                        SET is_active = 1,
                            added_date = CURRENT_TIMESTAMP
                        WHERE monitor_channel_id = ?
                        AND forward_channel_id = ?
                    ''', (monitor_channel_id, forward_channel_id))
            else:
                # 添加新配对
                self.cursor.execute('''
                    INSERT INTO channel_pairs
                    (monitor_channel_id, forward_channel_id)
                    VALUES (?, ?)
                ''', (monitor_channel_id, forward_channel_id))

            # 提交事务
            self.conn.commit()
            return True

        except sqlite3.Error as e:
            # 发生错误时回滚
            self.conn.rollback()
            logging.error(f"Error in add_channel_pair: {e}")
            return False

    def remove_channel_pair(self, monitor_channel_id: int, forward_channel_id: int) -> bool:
        """移除频道配对"""
        try:
            self.cursor.execute('''
                UPDATE channel_pairs
                SET is_active = 0,
                    added_date = CURRENT_TIMESTAMP
                WHERE monitor_channel_id = ?
                AND forward_channel_id = ?
                AND is_active = 1
            ''', (monitor_channel_id, forward_channel_id))

            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"Error in remove_channel_pair: {e}")
            return False

    # 过滤规则相关方法
    def add_filter_rule(self, pair_id: str, rule_type: str, filter_mode: str, pattern: str) -> bool:
        """添加过滤规则

        Args:
            pair_id: 频道配对ID，格式为 "monitor_id:forward_id"
            rule_type: 规则类型，'WHITELIST' 或 'BLACKLIST'
            filter_mode: 过滤模式，'KEYWORD' 或 'REGEX'
            pattern: 过滤模式
        """
        try:
            self.cursor.execute(
                "INSERT INTO filter_rules (pair_id, rule_type, filter_mode, pattern) VALUES (?, ?, ?, ?)",
                (pair_id, rule_type, filter_mode, pattern)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logging.error(f"Error adding filter rule: {e}")
            return False

    def get_filter_rules(self, pair_id: str = None, monitor_id: int = None, forward_id: int = None) -> List[Dict]:
        """获取指定频道配对的过滤规则

        可以使用pair_id或者monitor_id+forward_id的组合来查询
        """
        try:
            # 如果提供了monitor_id和forward_id，生成pair_id
            if pair_id is None and monitor_id is not None and forward_id is not None:
                pair_id = f"{monitor_id}:{forward_id}"

            if pair_id is None:
                logging.error("get_filter_rules: 需要提供pair_id或者monitor_id+forward_id")
                return []

            self.cursor.execute(
                "SELECT * FROM filter_rules WHERE pair_id = ? AND is_active = 1",
                (pair_id,)
            )
            rules = self.cursor.fetchall()
            result = []
            for rule in rules:
                result.append({
                    'rule_id': rule[0],
                    'pair_id': rule[1],
                    'rule_type': rule[2],
                    'filter_mode': rule[3],
                    'pattern': rule[4],
                    'is_active': rule[5],
                    'created_at': rule[6],
                    'updated_at': rule[7]
                })
            return result
        except Exception as e:
            logging.error(f"Error getting filter rules: {e}")
            return []

    def remove_filter_rule(self, rule_id: int) -> bool:
        """删除过滤规则"""
        try:
            self.cursor.execute(
                "UPDATE filter_rules SET is_active = 0 WHERE rule_id = ?",
                (rule_id,)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logging.error(f"Error removing filter rule: {e}")
            return False

    # 时间设置相关方法
    def add_time_filter(self, pair_id: str, start_time: str, end_time: str, days_of_week: str, mode: str = 'ALLOW') -> bool:
        """添加时间过滤器

        Args:
            pair_id: 频道配对ID，格式为 "monitor_id:forward_id"
            start_time: 开始时间，格式为 "HH:MM"
            end_time: 结束时间，格式为 "HH:MM"
            days_of_week: 星期，格式为 "1,2,3,4,5,6,7"
            mode: 模式，'ALLOW' 或 'BLOCK'
        """
        try:
            self.cursor.execute(
                "INSERT INTO time_filters (pair_id, start_time, end_time, days_of_week, mode) VALUES (?, ?, ?, ?, ?)",
                (pair_id, start_time, end_time, days_of_week, mode)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logging.error(f"Error adding time filter: {e}")
            return False

    def get_time_filters(self, pair_id: str = None, monitor_id: int = None, forward_id: int = None) -> List[Dict]:
        """获取指定频道配对的时间过滤器

        可以使用pair_id或者monitor_id+forward_id的组合来查询
        """
        try:
            # 如果提供了monitor_id和forward_id，生成pair_id
            if pair_id is None and monitor_id is not None and forward_id is not None:
                pair_id = f"{monitor_id}:{forward_id}"

            if pair_id is None:
                logging.error("get_time_filters: 需要提供pair_id或者monitor_id+forward_id")
                return []

            self.cursor.execute(
                "SELECT * FROM time_filters WHERE pair_id = ? AND is_active = 1",
                (pair_id,)
            )
            filters = self.cursor.fetchall()
            result = []
            for filter in filters:
                result.append({
                    'filter_id': filter[0],
                    'pair_id': filter[1],
                    'start_time': filter[2],
                    'end_time': filter[3],
                    'days_of_week': filter[4],
                    'is_active': filter[5],
                    'mode': filter[6],
                    'created_at': filter[7],
                    'updated_at': filter[8]
                })
            return result
        except Exception as e:
            logging.error(f"Error getting time filters: {e}")
            return []

    def remove_time_filter(self, filter_id: int) -> bool:
        """删除时间过滤器"""
        try:
            self.cursor.execute(
                "UPDATE time_filters SET is_active = 0 WHERE filter_id = ?",
                (filter_id,)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logging.error(f"Error removing time filter: {e}")
            return False

    def get_all_channel_pairs(self) -> List[Dict]:
        """获取所有活跃的频道配对"""
        try:
            self.cursor.execute(
                """
                SELECT cp.monitor_channel_id, cp.forward_channel_id,
                       m.channel_name as monitor_name, f.channel_name as forward_name
                FROM channel_pairs cp
                JOIN channels m ON cp.monitor_channel_id = m.channel_id
                JOIN channels f ON cp.forward_channel_id = f.channel_id
                WHERE cp.is_active = 1
                """
            )
            pairs = self.cursor.fetchall()
            result = []
            for pair in pairs:
                result.append({
                    'monitor_id': pair[0],
                    'forward_id': pair[1],
                    'monitor_name': pair[2],
                    'forward_name': pair[3],
                    'pair_id': f"{pair[0]}:{pair[1]}"
                })
            return result
        except Exception as e:
            logging.error(f"Error getting all channel pairs: {e}")
            return []

    def get_channel_info(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """获取频道信息"""
        try:
            self.cursor.execute('''
                SELECT
                    channel_id,
                    channel_name,
                    channel_username,
                    channel_type,
                    added_date,
                    is_active
                FROM channels
                WHERE channel_id = ?
            ''', (channel_id,))

            row = self.cursor.fetchone()
            if row:
                return {
                    'channel_id': row[0],
                    'channel_name': row[1],
                    'channel_username': row[2],
                    'channel_type': row[3],
                    'added_date': row[4],
                    'is_active': row[5]
                }
            return None
        except sqlite3.Error as e:
            logging.error(f"Error in get_channel_info: {e}")
            return None

    def get_channel_stats(self, channel_id: int) -> Dict[str, Any]:
        """获取频道统计信息"""
        try:
            # 如果是监控频道，获取转发频道数量
            self.cursor.execute('''
                SELECT COUNT(*)
                FROM channel_pairs
                WHERE monitor_channel_id = ?
                AND is_active = 1
            ''', (channel_id,))
            forward_count = self.cursor.fetchone()[0]

            # 如果是转发频道，获取监控频道数量
            self.cursor.execute('''
                SELECT COUNT(*)
                FROM channel_pairs
                WHERE forward_channel_id = ?
                AND is_active = 1
            ''', (channel_id,))
            monitor_count = self.cursor.fetchone()[0]

            return {
                'forward_channel_count': forward_count,
                'monitor_channel_count': monitor_count
            }
        except sqlite3.Error as e:
            logging.error(f"Error in get_channel_stats: {e}")
            return {
                'forward_channel_count': 0,
                'monitor_channel_count': 0
            }

    # 过滤规则相关方法
    def add_filter_rule(self, monitor_id: int, forward_id: int, rule_type: str, filter_mode: str, pattern: str) -> bool:
        """添加过滤规则"""
        try:
            pair_id = f"{monitor_id}:{forward_id}"
            self.cursor.execute('''
                INSERT INTO filter_rules (pair_id, rule_type, filter_mode, pattern)
                VALUES (?, ?, ?, ?)
            ''', (pair_id, rule_type, filter_mode, pattern))
            self.conn.commit()
            return True
        except Exception as e:
            logging.error(f"添加过滤规则失败: {e}")
            return False

    # 已经合并到上面的get_filter_rules方法中

    def update_filter_rule(self, rule_id: int, rule_type: str = None, filter_mode: str = None,
                          pattern: str = None, is_active: bool = None) -> bool:
        """更新过滤规则"""
        try:
            update_fields = []
            params = []

            if rule_type is not None:
                update_fields.append("rule_type = ?")
                params.append(rule_type)

            if filter_mode is not None:
                update_fields.append("filter_mode = ?")
                params.append(filter_mode)

            if pattern is not None:
                update_fields.append("pattern = ?")
                params.append(pattern)

            if is_active is not None:
                update_fields.append("is_active = ?")
                params.append(1 if is_active else 0)

            if not update_fields:
                return False

            update_fields.append("updated_at = CURRENT_TIMESTAMP")

            query = f"UPDATE filter_rules SET {', '.join(update_fields)} WHERE rule_id = ?"
            params.append(rule_id)

            self.cursor.execute(query, params)
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            logging.error(f"更新过滤规则失败: {e}")
            return False

    def delete_filter_rule(self, rule_id: int) -> bool:
        """删除过滤规则"""
        try:
            self.cursor.execute("UPDATE filter_rules SET is_active = 0 WHERE rule_id = ?", (rule_id,))
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            logging.error(f"删除过滤规则失败: {e}")
            return False

    # 时间段设置相关方法
    def add_time_filter(self, monitor_id: int, forward_id: int, start_time: str, end_time: str,
                       days_of_week: str, mode: str = 'ALLOW') -> bool:
        """添加时间段设置"""
        try:
            pair_id = f"{monitor_id}:{forward_id}"
            self.cursor.execute('''
                INSERT INTO time_filters (pair_id, start_time, end_time, days_of_week, mode)
                VALUES (?, ?, ?, ?, ?)
            ''', (pair_id, start_time, end_time, days_of_week, mode))
            self.conn.commit()
            return True
        except Exception as e:
            logging.error(f"添加时间段设置失败: {e}")
            return False

    # 已经合并到上面的get_time_filters方法中

    def update_time_filter(self, filter_id: int, start_time: str = None, end_time: str = None,
                          days_of_week: str = None, mode: str = None, is_active: bool = None) -> bool:
        """更新时间段设置"""
        try:
            update_fields = []
            params = []

            if start_time is not None:
                update_fields.append("start_time = ?")
                params.append(start_time)

            if end_time is not None:
                update_fields.append("end_time = ?")
                params.append(end_time)

            if days_of_week is not None:
                update_fields.append("days_of_week = ?")
                params.append(days_of_week)

            if mode is not None:
                update_fields.append("mode = ?")
                params.append(mode)

            if is_active is not None:
                update_fields.append("is_active = ?")
                params.append(1 if is_active else 0)

            if not update_fields:
                return False

            update_fields.append("updated_at = CURRENT_TIMESTAMP")

            query = f"UPDATE time_filters SET {', '.join(update_fields)} WHERE filter_id = ?"
            params.append(filter_id)

            self.cursor.execute(query, params)
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            logging.error(f"更新时间段设置失败: {e}")
            return False

    def delete_time_filter(self, filter_id: int) -> bool:
        """删除时间段设置"""
        try:
            self.cursor.execute("UPDATE time_filters SET is_active = 0 WHERE filter_id = ?", (filter_id,))
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            logging.error(f"删除时间段设置失败: {e}")
            return False

    def cleanup(self):
        """清理并关闭数据库连接"""
        if self.conn:
            try:
                # 可以在这里添加一些清理工作
                self.conn.commit()
            except sqlite3.Error as e:
                logging.error(f"Error during cleanup: {e}")
            finally:
                self.conn.close()

    def check_database_health(self) -> bool:
        """检查数据库健康状态"""
        try:
            # 检查表是否存在
            tables = ['channels', 'channel_pairs', 'user_preferences']
            for table in tables:
                self.cursor.execute(f"SELECT 1 FROM {table} LIMIT 1")

            # 检查索引是否存在
            self.cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='index' AND sql IS NOT NULL
            """)

            return True
        except sqlite3.Error as e:
            logging.error(f"Database health check failed: {e}")
            return False

    def optimize_database(self):
        """优化数据库"""
        try:
            self.cursor.executescript('''
                PRAGMA optimize;
                VACUUM;
                ANALYZE;
            ''')
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"Database optimization failed: {e}")
            return False

    def save_forwarded_message(self, original_chat_id: int, original_message_id: int,
                              forwarded_chat_id: int, forwarded_message_id: int) -> bool:
        """保存消息转发关系"""
        try:
            query = """
            INSERT OR REPLACE INTO forwarded_messages
            (original_chat_id, original_message_id, forwarded_chat_id, forwarded_message_id)
            VALUES (?, ?, ?, ?)
            """
            self.cursor.execute(query, (original_chat_id, original_message_id,
                                      forwarded_chat_id, forwarded_message_id))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"保存消息转发关系失败: {e}")
            return False

    def get_forwarded_message(self, original_chat_id: int, original_message_id: int,
                             forwarded_chat_id: int) -> Optional[Dict[str, Any]]:
        """获取转发消息关系"""
        try:
            query = """
            SELECT * FROM forwarded_messages
            WHERE original_chat_id = ? AND original_message_id = ? AND forwarded_chat_id = ?
            """
            self.cursor.execute(query, (original_chat_id, original_message_id, forwarded_chat_id))
            result = self.cursor.fetchone()
            if result:
                return {
                    'original_chat_id': result[0],
                    'original_message_id': result[1],
                    'forwarded_chat_id': result[2],
                    'forwarded_message_id': result[3],
                    'created_at': result[4]
                }
            return None
        except sqlite3.Error as e:
            logging.error(f"获取转发消息关系失败: {e}")
            return None