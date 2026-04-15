"""
Database module for credit management system.
Handles SQLite database operations for credits, models, groups, and transactions.
"""

import sqlite3
import os
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from app.config import DB_FILE, CREDIT_DATABASE_URL, DATABASE_URL

# PostgreSQL support
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

# Ne    # ...existing code...path (separate from OpenWebUI)
CREDITS_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "credits.db")

class CreditDatabase:
    def __init__(self, db_path: str = CREDITS_DB_PATH):
        if CREDIT_DATABASE_URL and POSTGRES_AVAILABLE:
            self.db_type = 'postgresql'
            self.connection_string = CREDIT_DATABASE_URL
        else:
            self.db_type = 'sqlite'
            self.db_path = db_path
        self.init_database()
    
    def get_placeholder(self):
        """Get the correct placeholder for the database type"""
        # For PostgreSQL / psycopg2 we use '%s' placeholders, for sqlite3 we use '?'
        return '%s' if self.db_type == 'postgresql' else '?'
    
    def execute_query(self, query: str, params: tuple = ()):  # -> cursor-like
        """Execute a query with proper parameter formatting for the database type"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Support queries written with either '?' or '%s' placeholders.
            # For PostgreSQL we need '%s', for SQLite we need '?'. Normalize accordingly.
            if self.db_type == 'postgresql':
                # Convert '?' placeholders to '%s' for psycopg2
                query = query.replace('?', '%s')
            else:
                # Convert '%s' placeholders to '?' for sqlite3
                if '%s' in query:
                    query = query.replace('%s', '?')
            cursor.execute(query, params)
            conn.commit()
            return cursor
    
    def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch one row with proper parameter formatting"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                query = query.replace('?', '%s')
            else:
                if '%s' in query:
                    query = query.replace('%s', '?')
            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Fetch all rows with proper parameter formatting"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                query = query.replace('?', '%s')
            else:
                if '%s' in query:
                    query = query.replace('%s', '?')
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        if self.db_type == 'postgresql':
            conn = psycopg2.connect(self.connection_string)
            conn.cursor_factory = RealDictCursor
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Enable column access by name
        try:
            yield conn
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if self.db_type == 'postgresql':
                # PostgreSQL schema with SERIAL and proper defaults
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_users (
                        id TEXT PRIMARY KEY,
                        balance REAL NOT NULL DEFAULT 0.0,
                        last_applied_default_credits REAL NOT NULL DEFAULT 0.0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_groups (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        default_credits REAL NOT NULL DEFAULT 0.0,
                        is_system_group BOOLEAN NOT NULL DEFAULT false,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_user_groups (
                        id SERIAL PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        group_id TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, group_id),
                        FOREIGN KEY (user_id) REFERENCES credit_users(id) ON DELETE CASCADE,
                        FOREIGN KEY (group_id) REFERENCES credit_groups(id) ON DELETE CASCADE
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_models (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        context_price REAL NOT NULL DEFAULT 0.001,
                        generation_price REAL NOT NULL DEFAULT 0.004,
                        is_available BOOLEAN NOT NULL DEFAULT true,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Add columns if they don't exist
                try:
                    cursor.execute("ALTER TABLE credit_models ADD COLUMN IF NOT EXISTS is_free BOOLEAN NOT NULL DEFAULT false")
                except:
                    pass
                try:
                    cursor.execute("ALTER TABLE credit_models ADD COLUMN IF NOT EXISTS is_restricted BOOLEAN NOT NULL DEFAULT false")
                except:
                    pass
                try:
                    cursor.execute("ALTER TABLE credit_groups ADD COLUMN IF NOT EXISTS is_system_group BOOLEAN NOT NULL DEFAULT false")
                except:
                    pass
                
                cursor.execute("""
                    INSERT INTO credit_groups (id, name, default_credits, is_system_group)
                    VALUES ('default', 'Default Users', 0.0, true)
                    ON CONFLICT (id) DO NOTHING
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_transactions (
                        id SERIAL PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        amount REAL NOT NULL,
                        transaction_type TEXT NOT NULL,
                        reason TEXT,
                        actor TEXT,
                        balance_after REAL NOT NULL,
                        model_id TEXT,
                        prompt_tokens INTEGER,
                        completion_tokens INTEGER,
                        cached_tokens INTEGER,
                        reasoning_tokens INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                try:
                    cursor.execute("ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS cached_tokens INTEGER")
                except:
                    pass
                try:
                    cursor.execute("ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS reasoning_tokens INTEGER")
                except:
                    pass
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_logs (
                        id SERIAL PRIMARY KEY,
                        log_type TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        message TEXT,
                        metadata TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    INSERT INTO credit_settings (key, value) 
                    VALUES ('usd_to_credit_ratio', '1000.0')
                    ON CONFLICT (key) DO NOTHING
                """)
                
                cursor.execute("""
                    INSERT INTO credit_settings (key, value) 
                    VALUES ('token_multiplier', '1000')
                    ON CONFLICT (key) DO NOTHING
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_reset_tracking (
                        id SERIAL PRIMARY KEY,
                        reset_type TEXT NOT NULL,
                        reset_date DATE NOT NULL,
                        reset_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        users_affected INTEGER NOT NULL DEFAULT 0,
                        total_credits_reset REAL NOT NULL DEFAULT 0.0,
                        status TEXT NOT NULL DEFAULT 'completed',
                        error_message TEXT,
                        metadata TEXT
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_usage_statistics (
                        id SERIAL PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        year INTEGER NOT NULL,
                        month INTEGER NOT NULL,
                        credits_used REAL NOT NULL DEFAULT 0.0,
                        transactions_count INTEGER NOT NULL DEFAULT 0,
                        models_used TEXT,
                        balance_before_reset REAL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, year, month)
                    )
                """)
                
                try:
                    cursor.execute("ALTER TABLE credit_usage_statistics ADD COLUMN IF NOT EXISTS balance_before_reset REAL")
                except:
                    pass

                # Add last_applied_default_credits column if it doesn't exist
                try:
                    cursor.execute("ALTER TABLE credit_users ADD COLUMN IF NOT EXISTS last_applied_default_credits REAL NOT NULL DEFAULT 0.0")
                except:
                    pass

                # Indexes
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_credit_user_groups_user ON credit_user_groups(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_credit_user_groups_group ON credit_user_groups(group_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON credit_transactions(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_model ON credit_transactions(model_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_type ON credit_logs(log_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reset_tracking_date ON credit_reset_tracking(reset_date)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reset_tracking_type ON credit_reset_tracking(reset_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_stats_user ON credit_usage_statistics(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_stats_date ON credit_usage_statistics(year, month)")
                
                # Waiting list table for public registrations (PostgreSQL)
                # Store only plaintext passwords per user request (primary deployment is Postgres)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_waiting_list (
                        id SERIAL PRIMARY KEY,
                        full_name TEXT NOT NULL,
                        email TEXT NOT NULL UNIQUE,
                        password_plain TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        processed BOOLEAN NOT NULL DEFAULT false,
                        processed_at TIMESTAMP
                    )
                """)

                try:
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_waiting_list_email ON credit_waiting_list(email)")
                except Exception:
                    pass
                # Ensure columns exist for older databases and remove password_hash if present
                try:
                    cursor.execute("ALTER TABLE credit_waiting_list ADD COLUMN IF NOT EXISTS processed BOOLEAN NOT NULL DEFAULT false")
                except Exception:
                    pass
                try:
                    cursor.execute("ALTER TABLE credit_waiting_list ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP")
                except Exception:
                    pass
                try:
                    cursor.execute("ALTER TABLE credit_waiting_list ADD COLUMN IF NOT EXISTS password_plain TEXT")
                except Exception:
                    pass
                # If an older DB still has password_hash, drop it (Postgres supports DROP COLUMN IF EXISTS)
                try:
                    cursor.execute("ALTER TABLE credit_waiting_list DROP COLUMN IF EXISTS password_hash")
                except Exception:
                    pass
            else:
                # SQLite schema (existing)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_users (
                        id TEXT PRIMARY KEY,
                        balance REAL NOT NULL DEFAULT 0.0,
                        last_applied_default_credits REAL DEFAULT 0.0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_groups (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        default_credits REAL NOT NULL DEFAULT 0.0,
                        is_system_group BOOLEAN NOT NULL DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_user_groups (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        group_id TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, group_id),
                        FOREIGN KEY (user_id) REFERENCES credit_users(id) ON DELETE CASCADE,
                        FOREIGN KEY (group_id) REFERENCES credit_groups(id) ON DELETE CASCADE
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_models (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        context_price REAL NOT NULL DEFAULT 0.001,
                        generation_price REAL NOT NULL DEFAULT 0.004,
                        is_available BOOLEAN NOT NULL DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                try:
                    cursor.execute("ALTER TABLE credit_models ADD COLUMN is_available BOOLEAN NOT NULL DEFAULT 1")
                except sqlite3.OperationalError:
                    pass
                
                try:
                    cursor.execute("ALTER TABLE credit_models ADD COLUMN is_free BOOLEAN NOT NULL DEFAULT 0")
                except sqlite3.OperationalError:
                    pass
                
                try:
                    cursor.execute("ALTER TABLE credit_models ADD COLUMN is_restricted BOOLEAN NOT NULL DEFAULT 0")
                except sqlite3.OperationalError:
                    pass
                
                try:
                    cursor.execute("ALTER TABLE credit_groups ADD COLUMN is_system_group BOOLEAN NOT NULL DEFAULT 0")
                except sqlite3.OperationalError:
                    pass
                
                cursor.execute("""
                    INSERT OR IGNORE INTO credit_groups (id, name, default_credits, is_system_group)
                    VALUES ('default', 'Default Users', 0.0, 1)
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        amount REAL NOT NULL,
                        transaction_type TEXT NOT NULL,
                        reason TEXT,
                        actor TEXT,
                        balance_after REAL NOT NULL,
                        model_id TEXT,
                        prompt_tokens INTEGER,
                        completion_tokens INTEGER,
                        cached_tokens INTEGER,
                        reasoning_tokens INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                try:
                    cursor.execute("ALTER TABLE credit_transactions ADD COLUMN cached_tokens INTEGER")
                except sqlite3.OperationalError:
                    pass
                
                try:
                    cursor.execute("ALTER TABLE credit_transactions ADD COLUMN reasoning_tokens INTEGER")
                except sqlite3.OperationalError:
                    pass
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        log_type TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        message TEXT,
                        metadata TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    INSERT OR IGNORE INTO credit_settings (key, value) 
                    VALUES ('usd_to_credit_ratio', '1000.0')
                """)
                
                cursor.execute("""
                    INSERT OR IGNORE INTO credit_settings (key, value) 
                    VALUES ('token_multiplier', '1000')
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_reset_tracking (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        reset_type TEXT NOT NULL,
                        reset_date DATE NOT NULL,
                        reset_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        users_affected INTEGER NOT NULL DEFAULT 0,
                        total_credits_reset REAL NOT NULL DEFAULT 0.0,
                        status TEXT NOT NULL DEFAULT 'completed',
                        error_message TEXT,
                        metadata TEXT
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_usage_statistics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        year INTEGER NOT NULL,
                        month INTEGER NOT NULL,
                        credits_used REAL NOT NULL DEFAULT 0.0,
                        transactions_count INTEGER NOT NULL DEFAULT 0,
                        models_used TEXT,
                        balance_before_reset REAL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, year, month)
                    )
                """)
                
                try:
                    cursor.execute("ALTER TABLE credit_usage_statistics ADD COLUMN balance_before_reset REAL")
                except sqlite3.OperationalError:
                    pass

                # Add last_applied_default_credits column if it doesn't exist
                try:
                    cursor.execute("ALTER TABLE credit_users ADD COLUMN last_applied_default_credits REAL DEFAULT 0.0")
                except sqlite3.OperationalError:
                    pass

                # Create waiting list table for SQLite (with processed fields)
                # Use plaintext password field to match Postgres schema (per user request)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS credit_waiting_list (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        full_name TEXT NOT NULL,
                        email TEXT NOT NULL UNIQUE,
                        password_plain TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        processed INTEGER NOT NULL DEFAULT 0,
                        processed_at TIMESTAMP
                    )
                """)

                # Migrate older SQLite DBs that may not have the new columns
                try:
                    cursor.execute("ALTER TABLE credit_waiting_list ADD COLUMN processed INTEGER NOT NULL DEFAULT 0")
                except sqlite3.OperationalError:
                    pass
                try:
                    cursor.execute("ALTER TABLE credit_waiting_list ADD COLUMN processed_at TIMESTAMP")
                except sqlite3.OperationalError:
                    pass
                
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_credit_user_groups_user ON credit_user_groups(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_credit_user_groups_group ON credit_user_groups(group_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON credit_transactions(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_model ON credit_transactions(model_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_type ON credit_logs(log_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reset_tracking_date ON credit_reset_tracking(reset_date)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reset_tracking_type ON credit_reset_tracking(reset_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_stats_user ON credit_usage_statistics(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_stats_date ON credit_usage_statistics(year, month)")
            
            conn.commit()
    
    # User operations
    def get_user_credits(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's credit information with all group memberships"""
        with self.get_connection() as conn:
            # Get user basic info
            user_row = self.fetch_one("SELECT * FROM credit_users WHERE id = %s", (user_id,))
            if not user_row:
                return None

            user_data = dict(user_row)
            
            # Get all group memberships (including default group)
            groups = self.fetch_all("""
                SELECT cg.id, cg.name, cg.default_credits, cg.is_system_group
                FROM credit_groups cg
                JOIN credit_user_groups cug ON cg.id = cug.group_id
                WHERE cug.user_id = %s
                ORDER BY cg.name
            """, (user_id,))
            
            # Ensure default group is always included (in memory)
            default_group_exists = any(g['id'] == 'default' for g in groups)
            if not default_group_exists:
                # Get default group info and add it
                default_group_row = self.fetch_one("""
                    SELECT id, name, default_credits, is_system_group
                    FROM credit_groups WHERE id = 'default'
                """)
                if default_group_row:
                    groups.append(dict(default_group_row))
            
            user_data['groups'] = groups
            
            # Calculate total default credits from ALL groups (including system groups)
            total_default_credits = sum(group['default_credits'] for group in groups)
            user_data['total_default_credits'] = total_default_credits
            
            # For UI display, exclude system groups from group_name but include all credits in default_credits
            display_groups = [g for g in groups if not g['is_system_group']]
            if display_groups:
                user_data['group_name'] = ', '.join([g['name'] for g in display_groups])
            else:
                user_data['group_name'] = None
            
            # Always include ALL group credits (including default/system groups) for reset logic
            user_data['default_credits'] = total_default_credits
            
            return user_data
    
    def get_all_users_with_credits(self) -> List[Dict[str, Any]]:
        """Get all users with their credit information and group memberships"""
        with self.get_connection() as conn:
            # Get all users
            users = self.fetch_all("SELECT * FROM credit_users ORDER BY id")
            
            # Get default group info once
            default_group_row = self.fetch_one("""
                SELECT id, name, default_credits, is_system_group
                FROM credit_groups WHERE id = 'default'
            """)
            default_group_dict = dict(default_group_row) if default_group_row else None
            
            # Get group memberships for all users
            for user in users:
                user_id = user['id']
                groups = self.fetch_all("""
                    SELECT cg.id, cg.name, cg.default_credits, cg.is_system_group
                    FROM credit_groups cg
                    JOIN credit_user_groups cug ON cg.id = cug.group_id
                    WHERE cug.user_id = %s
                    ORDER BY cg.name
                """, (user_id,))
                
                # Ensure default group is always included (in memory)
                default_group_exists = any(g['id'] == 'default' for g in groups)
                if not default_group_exists and default_group_dict:
                    groups.append(default_group_dict)
                
                user['groups'] = groups
                
                # Calculate total default credits from ALL groups (including default/system groups)
                total_default_credits = sum(group['default_credits'] for group in groups)
                user['total_default_credits'] = total_default_credits
                
                # For UI display, exclude system groups from group_name
                display_groups = [g for g in groups if not g['is_system_group']]
                if display_groups:
                    user['group_name'] = ', '.join([g['name'] for g in display_groups])
                else:
                    user['group_name'] = None
                
                # Always include ALL group credits (including default/system groups) for reset logic
                user['default_credits'] = total_default_credits
            
            return users
    
    def update_user_credits(self, user_id: str, new_balance: float, actor: str = "system", 
                           transaction_type: str = "update", reason: str = "") -> bool:
        """Update user's credit balance"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Update balance (create user if doesn't exist)
            self.execute_query("""
                INSERT INTO credit_users (id, balance, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    balance = EXCLUDED.balance,
                    updated_at = CURRENT_TIMESTAMP
            """, (user_id, new_balance))
            
            # Log transaction
            self.execute_query("""
                INSERT INTO credit_transactions 
                (user_id, amount, transaction_type, reason, actor, balance_after)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, new_balance, transaction_type, reason, actor, new_balance))
            
            conn.commit()
            return True
    
    def deduct_credits(self, user_id: str, amount: float, actor: str = "system",
                      reason: str = "", model_id: Optional[str] = None, 
                      prompt_tokens: Optional[int] = None, completion_tokens: Optional[int] = None,
                      cached_tokens: Optional[int] = None, reasoning_tokens: Optional[int] = None) -> tuple[float, float]:
        """Deduct credits from user and return (deducted_amount, new_balance)"""
        with self.get_connection() as conn:
            # Get current balance
            row = self.fetch_one("SELECT balance FROM credit_users WHERE id = %s", (user_id,))
            current_balance = row['balance'] if row else 0.0
            # Calculate actual deduction
            deducted = min(current_balance, amount)
            new_balance = max(0.0, current_balance - amount)
            # Update balance
            self.execute_query("""
                UPDATE credit_users SET balance = %s, updated_at = CURRENT_TIMESTAMP 
                WHERE id = %s
            """, (new_balance, user_id))
            # Log transaction
            self.execute_query("""
                INSERT INTO credit_transactions 
                (user_id, amount, transaction_type, reason, actor, balance_after, model_id, prompt_tokens, completion_tokens, cached_tokens, reasoning_tokens)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (user_id, -deducted, "deduct", reason, actor, new_balance, model_id, prompt_tokens, completion_tokens, cached_tokens, reasoning_tokens))
            conn.commit()
            
            # Update usage statistics (only if credits were actually deducted)
            if deducted > 0:
                self.update_usage_statistics(user_id, deducted, model_id)
            
            return deducted, new_balance
    
    def add_user_to_group(self, user_id: str, group_id: str) -> bool:
        """Add user to a group"""
        self.execute_query("""
            INSERT INTO credit_user_groups (user_id, group_id)
            VALUES (%s, %s)
            ON CONFLICT (user_id, group_id) DO NOTHING
        """, (user_id, group_id))
        return True
    
    def remove_user_from_group(self, user_id: str, group_id: str) -> bool:
        """Remove user from a group"""
        self.execute_query("""
            DELETE FROM credit_user_groups
            WHERE user_id = %s AND group_id = %s
        """, (user_id, group_id))
        return True
    
    def set_user_groups(self, user_id: str, group_ids: List[str]) -> bool:
        """Set user's group memberships (replaces all existing memberships)"""
        with self.get_connection() as conn:
            # Remove all existing memberships
            self.execute_query("DELETE FROM credit_user_groups WHERE user_id = %s", (user_id,))
            
            # Add new memberships
            for group_id in group_ids:
                self.execute_query("""
                    INSERT INTO credit_user_groups (user_id, group_id)
                    VALUES (%s, %s)
                """, (user_id, group_id))
            
            conn.commit()
            return True
    
    def get_user_groups(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all groups for a user"""
        return self.fetch_all("""
            SELECT cg.*
            FROM credit_groups cg
            JOIN credit_user_groups cug ON cg.id = cug.group_id
            WHERE cug.user_id = %s
            ORDER BY cg.name
        """, (user_id,))
    
    def assign_users_without_groups_to_default(self) -> int:
        """Assign users without any group memberships to the default system group"""
        with self.get_connection() as conn:
            # Find users without any group memberships
            users_without_groups = self.fetch_all("""
                SELECT u.id 
                FROM credit_users u
                LEFT JOIN credit_user_groups ug ON u.id = ug.user_id
                WHERE ug.user_id IS NULL
            """)
            
            assigned_count = 0
            
            for user_row in users_without_groups:
                user_id = user_row['id']
                self.execute_query("""
                    INSERT INTO credit_user_groups (user_id, group_id)
                    VALUES (%s, 'default')
                    ON CONFLICT (user_id, group_id) DO NOTHING
                """, (user_id,))
                assigned_count += 1
            
            conn.commit()
            
            if assigned_count > 0:
                self.log_action("auto_assign_default_group", "system", 
                              f"Assigned {assigned_count} users without groups to default group")
            
            return assigned_count
    
    def sync_groups_from_openwebui(self) -> int:
        """Sync groups from OpenWebUI database and return number of groups synced"""
        if not DATABASE_URL and not DB_FILE:
            print("❌ OpenWebUI database not configured (DATABASE_URL or OPENWEBUI_DATABASE_PATH environment variable)")
            return 0
            
        conn = None
        try:
            if DATABASE_URL:
                conn = psycopg2.connect(DATABASE_URL)
                cursor = conn.cursor()
                print("🔗 Using PostgreSQL for OpenWebUI group sync")
            else:
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                print(f"🔗 Using SQLite for OpenWebUI group sync: {DB_FILE}")
            
            # Use proper identifier quoting: PostgreSQL requires double quotes for reserved words,
            # SQLite uses plain identifiers (no single quotes).
            table_name = "\"group\"" if DATABASE_URL else "group"
            cursor.execute(f"SELECT id, name, description FROM {table_name}")
            openwebui_groups = cursor.fetchall()
            
            synced_count = 0
            with self.get_connection() as conn_credit:
                cursor_credit = conn_credit.cursor()
                
                for group in openwebui_groups:
                    if DATABASE_URL:
                        group_id = group[0]
                        group_name = group[1] or group_id
                    else:
                        group_id = group["id"]
                        group_name = group["name"] or group_id
                    
                    # Check if group exists (using PostgreSQL helper)
                    exists = self.fetch_one("SELECT id FROM credit_groups WHERE id = %s", (group_id,))
                    
                    if not exists:
                        # Create new group with default 1000 credits (OpenWebUI groups are not system groups)
                        self.execute_query("""
                            INSERT INTO credit_groups (id, name, default_credits, is_system_group)
                            VALUES (%s, %s, %s, %s)
                        """, (group_id, group_name, 1000.0, False))
                        synced_count += 1
                        print(f"✅ Created new group: {group_name} ({group_id})")
                    else:
                        # Update group name if needed, but preserve is_system_group flag
                        self.execute_query("""
                            UPDATE credit_groups SET name = %s WHERE id = %s
                        """, (group_name, group_id))
                
                conn_credit.commit()
            
            if synced_count > 0:
                self.log_action("group_sync", "system", f"Synced {synced_count} groups from OpenWebUI")
            
            return synced_count
            
        except Exception as e:
            print(f"Error syncing groups from OpenWebUI: {e}")
            self.log_action("group_sync_error", "system", f"Failed to sync groups: {str(e)}")
            return 0
        finally:
            if conn:
                conn.close()
    
    def sync_user_groups_from_openwebui(self, user_id: str) -> bool:
        """Sync a specific user's group memberships from OpenWebUI"""
        if not DATABASE_URL and not DB_FILE:
            print("❌ OpenWebUI database not configured (DATABASE_URL or OPENWEBUI_DATABASE_PATH environment variable)")
            return False

        conn = None
        try:
            if DATABASE_URL:
                conn = psycopg2.connect(DATABASE_URL)
                cursor = conn.cursor()
            else:
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

            table_name = '"group"' if DATABASE_URL else 'group'

            # Build mapping only for the single user using the same heuristics as the bulk sync
            user_group_ids: List[str] = []

            try:
                # FIRST: Try group_member join table (OpenWebUI's actual schema)
                try:
                    cursor.execute(
                        "SELECT group_id FROM group_member WHERE user_id = %s" if DATABASE_URL
                        else "SELECT group_id FROM group_member WHERE user_id = ?",
                        (user_id,)
                    )
                    gm_rows = cursor.fetchall()
                    if gm_rows:
                        print(f"✅ Using group_member table for user {user_id}")
                        for r in gm_rows:
                            gid = r[0] if DATABASE_URL else r['group_id']
                            user_group_ids.append(gid)
                except Exception:
                    pass  # Fall through to other methods if group_member doesn't exist

                # If we already have memberships from group_member, skip the rest
                if not user_group_ids:
                    # Fallback: try to read from group table directly
                    cursor.execute(f"SELECT * FROM {table_name}")
                    rows = cursor.fetchall()
                    cols = [d[0] for d in cursor.description]
                    candidate_cols = [c for c in ['user_ids', 'users', 'members', 'member_ids', 'user_list'] if c in cols]

                    if candidate_cols:
                        col = candidate_cols[0]
                        col_idx = {name: i for i, name in enumerate(cols)}
                        id_idx = col_idx.get('id', 0)
                        for row in rows:
                            group_id = row[id_idx] if DATABASE_URL else row['id']
                            user_ids_val = row[col_idx[col]] if DATABASE_URL else row[col]
                            if not user_ids_val:
                                continue
                            try:
                                if isinstance(user_ids_val, str):
                                    parsed = json.loads(user_ids_val.strip())
                                else:
                                    parsed = list(user_ids_val)
                            except (json.JSONDecodeError, TypeError, ValueError):
                                continue
                            if user_id in parsed:
                                user_group_ids.append(group_id)
                    else:
                        # Try other join table candidates (excluding group_member which we already tried)
                        join_table_candidates = ['group_user', 'user_group', 'group_members', 'group_users', 'user_groups']
                        found = False
                        for jt in join_table_candidates:
                            try:
                                cursor.execute(
                                    f"SELECT group_id FROM {jt} WHERE user_id = %s" if DATABASE_URL
                                    else f"SELECT group_id FROM {jt} WHERE user_id = ?",
                                    (user_id,)
                                )
                                jt_rows = cursor.fetchall()
                                if jt_rows:
                                    for r in jt_rows:
                                        gid = r[0] if DATABASE_URL else r['group_id']
                                        user_group_ids.append(gid)
                                    found = True
                                    break
                            except Exception:
                                continue

                        if not found:
                            # Fallback: check user table for group/group_id
                            try:
                                user_query = f"SELECT group, group_id FROM \"user\" WHERE id = %s" if DATABASE_URL else "SELECT group, group_id FROM user WHERE id = ?"
                                cursor.execute(user_query, (user_id,))
                                ur = cursor.fetchone()
                                if ur:
                                    if DATABASE_URL:
                                        group_val = ur[0] or ur[1]
                                    else:
                                        group_val = ur['group'] or ur.get('group_id')
                                    if group_val:
                                        try:
                                            if isinstance(group_val, str) and (group_val.strip().startswith('[') or group_val.strip().startswith('{')):
                                                parsed = json.loads(group_val)
                                                if isinstance(parsed, list):
                                                    user_group_ids.extend(parsed)
                                                elif isinstance(parsed, dict):
                                                    ids = parsed.get('group_ids') or parsed.get('user_ids')
                                                    if isinstance(ids, list):
                                                        user_group_ids.extend(ids)
                                            else:
                                                user_group_ids.append(str(group_val))
                                        except Exception:
                                            user_group_ids.append(str(group_val))
                            except Exception:
                                pass

                # Persist memberships
                self.set_user_groups(user_id, user_group_ids)
                return True
            except Exception as e:
                print(f"Error syncing user groups for {user_id}: {e}")
                return False
        finally:
            if conn:
                conn.close()

    def sync_all_user_groups_from_openwebui(self) -> int:
        """Sync all user group memberships from OpenWebUI"""
        if not DATABASE_URL and not DB_FILE:
            print("❌ OpenWebUI database not configured (DATABASE_URL or OPENWEBUI_DATABASE_PATH environment variable)")
            return 0

        conn = None
        try:
            if DATABASE_URL:
                conn = psycopg2.connect(DATABASE_URL)
                cursor = conn.cursor()
                print("🔗 Using PostgreSQL for OpenWebUI user-groups sync")
            else:
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                print(f"🔗 Using SQLite for OpenWebUI user-groups sync: {DB_FILE}")

            table_name = '"group"' if DATABASE_URL else 'group'

            # Build user -> groups mapping
            user_groups_map: Dict[str, List[str]] = {}

            try:
                # FIRST: Try group_member join table (OpenWebUI's actual schema)
                # OpenWebUI uses a separate group_member table for many-to-many relationships
                try:
                    cursor.execute("SELECT group_id, user_id FROM group_member")
                    gm_rows = cursor.fetchall()
                    if gm_rows:
                        print(f"✅ Using group_member table for user-group mappings")
                        for r in gm_rows:
                            if DATABASE_URL:
                                gid, uid = r[0], r[1]
                            else:
                                gid, uid = r['group_id'], r['user_id']
                            user_groups_map.setdefault(uid, []).append(gid)
                except Exception:
                    pass  # Fall through to other methods if group_member doesn't exist

                # If we already have mappings from group_member, skip the rest
                if user_groups_map:
                    # Still fetch groups for later processing
                    cursor.execute(f"SELECT * FROM {table_name}")
                    groups = cursor.fetchall()
                else:
                    # Fallback: try to read from group table directly
                    cursor.execute(f"SELECT * FROM {table_name}")
                    groups = cursor.fetchall()
                    cols = [d[0] for d in cursor.description]

                    candidate_cols = [c for c in ['user_ids', 'users', 'members', 'member_ids', 'user_list'] if c in cols]
                    if candidate_cols:
                        col = candidate_cols[0]
                        col_idx = {name: i for i, name in enumerate(cols)}
                        id_idx = col_idx.get('id', 0)

                        for row in groups:
                            group_id = row[id_idx] if DATABASE_URL else row['id']
                            user_ids_val = row[col_idx[col]] if DATABASE_URL else row[col]
                            if not user_ids_val:
                                continue
                            try:
                                if isinstance(user_ids_val, str):
                                    parsed = json.loads(user_ids_val.strip())
                                else:
                                    parsed = list(user_ids_val)
                            except (json.JSONDecodeError, TypeError, ValueError):
                                continue
                            for uid in parsed:
                                user_groups_map.setdefault(uid, []).append(group_id)
                    else:
                        # Try other join table candidates
                        join_table_candidates = ['group_user', 'user_group', 'group_members', 'group_users', 'user_groups']
                        found = False
                        for jt in join_table_candidates:
                            try:
                                cursor.execute(f"SELECT group_id, user_id FROM {jt}")
                                jt_rows = cursor.fetchall()
                                if jt_rows:
                                    for r in jt_rows:
                                        if DATABASE_URL:
                                            gid, uid = r[0], r[1]
                                        else:
                                            gid, uid = r['group_id'], r['user_id']
                                        user_groups_map.setdefault(uid, []).append(gid)
                                    found = True
                                    break
                            except Exception:
                                continue

                    if not found:
                        # Fallback: check user table for group/group_id field
                        try:
                            cursor.execute('SELECT * FROM "user"' if DATABASE_URL else 'SELECT * FROM user')
                            urows = cursor.fetchall()
                            ucols = [d[0] for d in cursor.description]
                            if 'group' in ucols or 'group_id' in ucols:
                                for ur in urows:
                                    if DATABASE_URL:
                                        uid = ur[ucols.index('id')]
                                        gval = None
                                        if 'group' in ucols:
                                            gval = ur[ucols.index('group')]
                                        elif 'group_id' in ucols:
                                            gval = ur[ucols.index('group_id')]
                                    else:
                                        uid = ur['id']
                                        gval = ur.get('group') or ur.get('group_id')
                                    if not gval:
                                        continue
                                    try:
                                        if isinstance(gval, str) and (gval.strip().startswith('[') or gval.strip().startswith('{')):
                                            parsed = json.loads(gval)
                                            if isinstance(parsed, list):
                                                for gid in parsed:
                                                    user_groups_map.setdefault(uid, []).append(gid)
                                            elif isinstance(parsed, dict):
                                                ids = parsed.get('group_ids') or parsed.get('user_ids')
                                                if isinstance(ids, list):
                                                    for gid in ids:
                                                        user_groups_map.setdefault(uid, []).append(gid)
                                        else:
                                            user_groups_map.setdefault(uid, []).append(str(gval))
                                    except Exception:
                                        user_groups_map.setdefault(uid, []).append(str(gval))
                        except Exception:
                            pass
            except Exception as e:
                print(f"Error building user-groups map: {e}")

            # First, ensure all groups exist in our database
            synced_groups = 0
            for group in groups:
                if DATABASE_URL:
                    group_id = group[0]
                    group_name = group[1] or group_id
                else:
                    group_id = group["id"]
                    group_name = group["name"] or group_id
                
                # Check if group exists
                exists = self.fetch_one("SELECT id FROM credit_groups WHERE id = %s", (group_id,))
                
                if not exists:
                    # Create new group with default 1000 credits (OpenWebUI groups are not system groups)
                    self.execute_query("""
                        INSERT INTO credit_groups (id, name, default_credits, is_system_group)
                        VALUES (%s, %s, %s, %s)
                    """, (group_id, group_name, 1000.0, False))
                    synced_groups += 1
                    print(f"✅ Created new group: {group_name} ({group_id})")
            
            if synced_groups > 0:
                print(f"✅ Synced {synced_groups} groups from OpenWebUI")

            # Update memberships for all users
            synced_count = 0
            with self.get_connection() as conn_credit:
                cursor_credit = conn_credit.cursor()

                # Clear all existing memberships
                self.execute_query("DELETE FROM credit_user_groups")

                # Add new memberships
                for uid, group_ids in user_groups_map.items():
                    # Ensure the user exists in our credit system before assigning groups
                    user_exists = self.fetch_one("SELECT id FROM credit_users WHERE id = %s", (uid,))
                    if not user_exists:
                        # Create the user with a sensible default balance (match other sync behavior)
                        self.update_user_credits(
                            user_id=uid,
                            new_balance=1000.0,
                            actor='sync',
                            transaction_type='sync',
                            reason='Created user during group membership sync from OpenWebUI'
                        )

                    for gid in group_ids:
                        self.execute_query("""
                            INSERT INTO credit_user_groups (user_id, group_id)
                            VALUES (%s, %s)
                        """, (uid, gid))
                    synced_count += 1

                conn_credit.commit()

            # Commented out to reduce log clutter - routine sync operation
            # self.log_action("user_groups_sync", "system", f"Synced group memberships for {synced_count} users")
            return synced_count
        except Exception as e:
            print(f"Error syncing all user groups: {e}")
            self.log_action("user_groups_sync_error", "system", f"Failed to sync user groups: {str(e)}")
            return 0
        finally:
            if conn:
                conn.close()

    def apply_group_credit_adjustments(self, force_all: bool = False) -> Dict[str, Any]:
        """
        Apply default credit changes to user balances based on current group memberships.

        For each user:
        - Calculate current total_default_credits (sum of all group defaults)
        - Compare with last_applied_default_credits stored in database
        - Add/remove the difference (additive adjustment): new_balance = current_balance + (new_default - old_default)
        - Update last_applied_default_credits to current value

        Args:
            force_all: If True, adjust ALL users. If False, only adjust users with changes.

        Returns:
            Dict with adjustment results (users_adjusted, total_adjustment, details)
        """
        from datetime import datetime, timezone

        # Get all users with their group memberships
        users = self.get_all_users_with_credits()

        users_adjusted = 0
        total_adjustment = 0.0
        details = []

        for user in users:
            user_id = user['id']
            current_balance = user['balance']
            current_default_credits = user.get('total_default_credits', 0)

            # Get last applied default credits
            last_applied = user.get('last_applied_default_credits', 0)
            if last_applied is None:
                last_applied = 0

            # Calculate adjustment needed
            adjustment = current_default_credits - last_applied

            # Skip if no adjustment needed and not forcing
            if adjustment == 0 and not force_all:
                continue

            # Calculate new balance (additive adjustment)
            new_balance = current_balance + adjustment

            # Apply the adjustment
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Update balance
                self.execute_query("""
                    UPDATE credit_users
                    SET balance = %s, last_applied_default_credits = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (new_balance, current_default_credits, user_id))

                # Log transaction
                sign = "+" if adjustment >= 0 else ""
                self.execute_query("""
                    INSERT INTO credit_transactions
                    (user_id, amount, transaction_type, reason, actor, balance_after)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    user_id,
                    adjustment,
                    'group_adjustment',
                    f'Group credit adjustment: {sign}{adjustment} credits',
                    'system',
                    new_balance
                ))

                conn.commit()

            users_adjusted += 1
            total_adjustment += adjustment

            # Get user name for details
            user_info = self.get_users_info_from_openwebui([user_id])
            user_name = user_info.get(user_id, {}).get('name', user_id)

            details.append({
                'user_id': user_id,
                'user_name': user_name,
                'adjustment': adjustment,
                'new_balance': new_balance,
                'old_default_credits': last_applied,
                'new_default_credits': current_default_credits
            })

            print(f"✅ Adjusted {user_name}: {sign}{adjustment} credits (balance: {new_balance})")

        # Log the overall adjustment
        if users_adjusted > 0:
            self.log_action(
                "group_credit_adjustment",
                "system",
                f"Applied group credit adjustments to {users_adjusted} users, total adjustment: {total_adjustment}",
                {"users_adjusted": users_adjusted, "total_adjustment": total_adjustment}
            )

        return {
            'users_adjusted': users_adjusted,
            'total_adjustment': total_adjustment,
            'details': details
        }

    # Model operations
    def get_model_pricing(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get model pricing information"""
        return self.fetch_one("SELECT * FROM credit_models WHERE id = %s", (model_id,))
    
    def get_all_models(self) -> List[Dict[str, Any]]:
        """Get all model pricing information"""
        return self.fetch_all("SELECT * FROM credit_models ORDER BY name")
    
    def update_model_availability(self, model_id: str, is_available: bool) -> bool:
        """Update model availability status only"""
        self.execute_query("""
            UPDATE credit_models SET is_available = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (is_available, model_id))
        return True

    def update_model_free_status(self, model_id: str, is_free: bool) -> bool:
        """Update model free status only"""
        self.execute_query("""
            UPDATE credit_models SET is_free = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (is_free, model_id))
        return True

    def update_model_restriction_status(self, model_id: str, is_restricted: bool) -> bool:
        """Update model restriction status only"""
        self.execute_query("""
            UPDATE credit_models SET is_restricted = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (is_restricted, model_id))
        return True

    def update_model_name(self, model_id: str, name: str) -> bool:
        """Update model name only"""
        self.execute_query("""
            UPDATE credit_models SET name = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (name, model_id))
        return True

    def update_model_pricing(self, model_id: str, name: str, context_price: float, 
                           generation_price: float, is_available: bool = True, is_free: bool = False, is_restricted: bool = False) -> bool:
        """Update model pricing, availability status, free status, and restriction status"""
        self.execute_query("""
            INSERT INTO credit_models (id, name, context_price, generation_price, is_available, is_free, is_restricted, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                context_price = EXCLUDED.context_price,
                generation_price = EXCLUDED.generation_price,
                is_available = EXCLUDED.is_available,
                is_free = EXCLUDED.is_free,
                is_restricted = EXCLUDED.is_restricted,
                updated_at = CURRENT_TIMESTAMP
        """, (model_id, name, context_price, generation_price, is_available, is_free, is_restricted))
        return True
    
    # Group operations
    def get_all_groups(self) -> List[Dict[str, Any]]:
        """Get all credit groups"""
        return self.fetch_all("SELECT * FROM credit_groups ORDER BY name")
    
    def update_group(self, group_id: str, name: str, default_credits: float, is_system_group: bool = False) -> bool:
        """Update group information"""
        self.execute_query("""
            INSERT INTO credit_groups (id, name, default_credits, is_system_group, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                default_credits = EXCLUDED.default_credits,
                is_system_group = EXCLUDED.is_system_group,
                updated_at = CURRENT_TIMESTAMP
        """, (group_id, name, default_credits, is_system_group))
        return True
    
    # Transaction history
    def get_user_transactions(self, user_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get user's transaction history with pagination"""
        with self.get_connection() as conn:
            # Get total count
            total_result = self.fetch_one("""
                SELECT COUNT(*) as total
                FROM credit_transactions ct
                WHERE ct.user_id = %s
            """, (user_id,))
            total = total_result['total'] if total_result else 0
            
            # Get paginated results
            transactions = self.fetch_all("""
                SELECT ct.*
                FROM credit_transactions ct
                WHERE ct.user_id = %s 
                ORDER BY ct.created_at DESC 
                LIMIT %s OFFSET %s
            """, (user_id, limit, offset))
            
            return {
                'transactions': transactions,
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_next': offset + limit < total,
                'has_prev': offset > 0
            }
    
    def get_all_transactions(self, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get all transactions with pagination"""
        with self.get_connection() as conn:
            # Get total count
            total_result = self.fetch_one("""
                SELECT COUNT(*) as total
                FROM credit_transactions ct
            """)
            total = total_result['total'] if total_result else 0
            
            # Get paginated results
            transactions = self.fetch_all("""
                SELECT ct.*
                FROM credit_transactions ct
                ORDER BY ct.created_at DESC 
                LIMIT %s OFFSET %s
            """, (limit, offset))
            
            return {
                'transactions': transactions,
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_next': offset + limit < total,
                'has_prev': offset > 0
            }
    
    # Logging
    def log_action(self, log_type: str, actor: str, message: str, metadata: Optional[Dict] = None):
        """Log system action"""
        self.execute_query("""
            INSERT INTO credit_logs (log_type, actor, message, metadata)
            VALUES (%s, %s, %s, %s)
        """, (log_type, actor, message, json.dumps(metadata) if metadata else None))
    
    def get_logs(self, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get system logs with pagination"""
        with self.get_connection() as conn:
            # Get total count
            total_result = self.fetch_one("""
                SELECT COUNT(*) as total
                FROM credit_logs
            """)
            total = total_result['total'] if total_result else 0
            
            # Get paginated results
            logs = self.fetch_all("""
                SELECT * FROM credit_logs 
                ORDER BY created_at DESC 
                LIMIT %s OFFSET %s
            """, (limit, offset))
            
            return {
                'logs': logs,
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_next': offset + limit < total,
                'has_prev': offset > 0
            }
    
    def delete_log_entry(self, log_id: int) -> bool:
        """Delete a specific log entry by ID"""
        self.execute_query("DELETE FROM credit_logs WHERE id = %s", (log_id,))
        return True

    def get_user_name_from_openwebui(self, user_id: str) -> Optional[str]:
        """Get user name from OpenWebUI database"""
        if not DATABASE_URL and not DB_FILE:
            return None
            
        conn = None
        try:
            if DATABASE_URL:
                conn = psycopg2.connect(DATABASE_URL)
                cursor = conn.cursor()
            else:
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
            
            table_name = "\"user\"" if DATABASE_URL else "user"
            if DATABASE_URL:
                cursor.execute(f"SELECT name, email FROM {table_name} WHERE id = %s", (user_id,))
            else:
                cursor.execute(f"SELECT name, email FROM {table_name} WHERE id = ?", (user_id,))
            
            row = cursor.fetchone()
            
            if row:
                if DATABASE_URL:
                    name = row[0]
                    email = row[1]
                else:
                    name = row["name"]
                    email = row["email"]
                return name if name else email
            return None
        except Exception as e:
            print(f"Error getting user name from OpenWebUI: {e}")
            return None
        finally:
            if conn:
                conn.close()
    
    def get_yearly_usage_summary(self, year):
        """Get yearly usage summary for a given year"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get aggregated statistics
                result = self.fetch_one("""
                    SELECT 
                        COALESCE(SUM(credits_used), 0) as total_credits_used,
                        COALESCE(SUM(transactions_count), 0) as total_transactions,
                        COUNT(DISTINCT user_id) as unique_users,
                        COUNT(*) as total_entries
                    FROM credit_usage_statistics 
                    WHERE year = %s
                """, (year,))
                
                if result and result["total_entries"] > 0:
                    # Count unique models
                    models_rows = self.fetch_all("""
                        SELECT models_used 
                        FROM credit_usage_statistics 
                        WHERE year = %s AND models_used IS NOT NULL
                    """, (year,))
                    
                    all_models = set()
                    for row in models_rows:
                        try:
                            models = json.loads(row["models_used"])
                            all_models.update(models)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    
                    summary = dict(result)
                    summary["unique_models"] = len(all_models)
                    return summary
                
                return None
        except Exception as e:
            print(f"Error getting yearly usage summary: {e}")
            return None
    
    def insert_dummy_statistics(self, user_id, year, month, credits_used, transactions_count, models_used, balance_before_reset=None):
        """Insert dummy statistics data for testing"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if entry already exists
                existing = self.fetch_one("""
                    SELECT id FROM credit_usage_statistics 
                    WHERE user_id = %s AND year = %s AND month = %s
                """, (user_id, year, month))
                
                if existing:
                    # Update existing entry
                    self.execute_query("""
                        UPDATE credit_usage_statistics 
                        SET credits_used = %s, transactions_count = %s, models_used = %s, balance_before_reset = %s
                        WHERE user_id = %s AND year = %s AND month = %s
                    """, (credits_used, transactions_count, json.dumps(models_used), balance_before_reset, user_id, year, month))
                else:
                    # Insert new entry
                    self.execute_query("""
                        INSERT INTO credit_usage_statistics 
                        (user_id, year, month, credits_used, transactions_count, models_used, balance_before_reset)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (user_id, year, month, credits_used, transactions_count, json.dumps(models_used), balance_before_reset))
                
                conn.commit()
                return True
        except Exception as e:
            print(f"Error inserting dummy statistics: {e}")
            return False
    
    def update_july_balance_before_reset(self):
        """Update July 2025 statistics with calculated balance_before_reset values"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get all July 2025 statistics entries
                july_stats = self.fetch_all("""
                    SELECT user_id, credits_used FROM credit_usage_statistics
                    WHERE year = %s AND month = %s
                """, (2025, 7))
                
                updated_count = 0
                
                for user_id, credits_used in july_stats:
                    # For dummy data, we'll assume they started with 900 credits (default group)
                    # and calculate what their balance would have been at end of July
                    starting_balance = 900.0  # Default credits for most users
                    balance_before_reset = max(0, starting_balance - credits_used)
                    
                    # Update the record
                    self.execute_query("""
                        UPDATE credit_usage_statistics 
                        SET balance_before_reset = %s
                        WHERE user_id = %s AND year = %s AND month = %s
                    """, (balance_before_reset, user_id, 2025, 7))
                    
                    updated_count += 1
                    print(f"Updated {user_id}: used {credits_used:.2f}, balance before reset: {balance_before_reset:.2f}")
                
                conn.commit()
                print(f"\n✅ Updated {updated_count} July 2025 records with balance_before_reset")
                return True
                
        except Exception as e:
            print(f"❌ Error updating July balance_before_reset: {e}")
            return False

    def get_users_info_from_openwebui(self, user_ids: Optional[List[str]] = None) -> Dict[str, Dict[str, str]]:
        """
        Get user information from OpenWebUI database.
        If user_ids is None, gets all users. Otherwise gets specific users.
        Returns dict with user_id as key and dict with name/email as value.
        """
        if not DATABASE_URL and not DB_FILE:
            return {}
            
        conn = None
        try:
            if DATABASE_URL:
                conn = psycopg2.connect(DATABASE_URL)
                cursor = conn.cursor()
                print("🔗 Using PostgreSQL for OpenWebUI user info fetch")
            else:
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                print(f"🔗 Using SQLite for OpenWebUI user info fetch: {DB_FILE}")
            
            table_name = "\"user\"" if DATABASE_URL else "user"
            
            if user_ids is None:
                # Get all users
                cursor.execute(f"SELECT id, name, email FROM {table_name}")
            else:
                # Get specific users
                if DATABASE_URL:
                    placeholders = ','.join(['%s'] * len(user_ids))
                    cursor.execute(f"SELECT id, name, email FROM {table_name} WHERE id IN ({placeholders})", user_ids)
                else:
                    placeholders = ','.join(['?'] * len(user_ids))
                    cursor.execute(f"SELECT id, name, email FROM {table_name} WHERE id IN ({placeholders})", user_ids)
            
            result = {}
            for row in cursor.fetchall():
                if DATABASE_URL:
                    # PostgreSQL: access by index
                    user_id = row[0]
                    name = row[1]
                    email = row[2]
                else:
                    # SQLite: access by name
                    user_id = row["id"]
                    name = row["name"]
                    email = row["email"]
                    
                result[user_id] = {
                    "name": name,
                    "email": email
                }
            
            return result
            
        except Exception as e:
            print(f"Error fetching user info from OpenWebUI: {e}")
            return {}
        finally:
            if conn:
                conn.close()
    
    def get_setting(self, key: str, default_value: Optional[str] = None) -> Optional[str]:
        """Get a setting value"""
        row = self.fetch_one("SELECT value FROM credit_settings WHERE key = %s", (key,))
        return row['value'] if row else default_value
    
    def set_setting(self, key: str, value: str) -> bool:
        """Set a setting value"""
        self.execute_query("""
            INSERT INTO credit_settings (key, value, updated_at) 
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = CURRENT_TIMESTAMP
        """, (key, value))
        return True
    
    def get_usd_to_credit_ratio(self) -> float:
        """Get the current USD to credit conversion ratio"""
        ratio_str = self.get_setting('usd_to_credit_ratio', '1000.0')
        try:
            return float(ratio_str) if ratio_str else 1000.0
        except (ValueError, TypeError):
            return 1000.0  # Default fallback
    
    def set_usd_to_credit_ratio(self, ratio: float) -> bool:
        """Set the USD to credit conversion ratio"""
        return self.set_setting('usd_to_credit_ratio', str(ratio))
    
    def credits_to_usd(self, credits: float) -> float:
        """Convert credits to USD"""
        ratio = self.get_usd_to_credit_ratio()
        return credits / ratio
    
    def usd_to_credits(self, usd: float) -> float:
        """Convert USD to credits"""
        ratio = self.get_usd_to_credit_ratio()
        return usd * ratio

    def get_token_multiplier(self) -> int:
        """Get the current token multiplier setting"""
        multiplier_str = self.get_setting('token_multiplier', '1000')
        try:
            return int(multiplier_str) if multiplier_str else 1000
        except (ValueError, TypeError):
            return 1000  # Default fallback

    def set_token_multiplier(self, multiplier: int) -> bool:
        """Set the token multiplier setting"""
        return self.set_setting('token_multiplier', str(multiplier))

    # Reset tracking methods
    def record_reset_event(self, reset_type: str, reset_date: str, users_affected: int, 
                          total_credits_reset: float, status: str = 'completed', 
                          error_message: Optional[str] = None, metadata: Optional[Dict] = None) -> int:
        """Record a credit reset event"""
        # Use explicit connection so we can obtain lastrowid for sqlite
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Normalize placeholder for DB type
            query = """
                INSERT INTO credit_reset_tracking 
                (reset_type, reset_date, users_affected, total_credits_reset, status, error_message, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            if self.db_type == 'postgresql':
                query_exec = query.replace('?', '%s')
            else:
                if '%s' in query:
                    query_exec = query.replace('%s', '?')
                else:
                    query_exec = query

            cursor.execute(query_exec, (
                reset_type,
                reset_date,
                users_affected,
                total_credits_reset,
                status,
                error_message,
                json.dumps(metadata) if metadata else None
            ))
            conn.commit()

            # Also log the event
            try:
                self.log_action(
                    log_type="reset_event",
                    actor="system",
                    message=f"Credit reset {reset_type} for {users_affected} users on {reset_date}",
                    metadata={"total_credits": total_credits_reset}
                )
            except Exception:
                pass

            # Return lastrowid where available (sqlite). For PostgreSQL we fall back to 0.
            try:
                return int(cursor.lastrowid) if cursor.lastrowid is not None else 0
            except Exception:
                return 0

    def get_last_reset_date(self, reset_type: str = 'monthly') -> Optional[str]:
        """Get the date of the last successful reset of the specified type"""
        row = self.fetch_one("""
            SELECT reset_date FROM credit_reset_tracking 
            WHERE reset_type = %s AND status = 'completed'
            ORDER BY reset_date DESC LIMIT 1
        """, (reset_type,))
        if not row:
            return None
        return row.get('reset_date') if isinstance(row, dict) else (row[0] if row else None)

    def get_reset_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get the history of credit resets"""
        results = self.fetch_all("""
            SELECT * FROM credit_reset_tracking 
            ORDER BY reset_timestamp DESC LIMIT %s
        """, (limit,))
        
        for result in results:
            if result['metadata']:
                try:
                    result['metadata'] = json.loads(result['metadata'])
                except json.JSONDecodeError:
                    result['metadata'] = {}
            else:
                result['metadata'] = {}
        return results

    def needs_monthly_reset(self) -> bool:
        """Check if a monthly reset is needed"""
        from datetime import datetime, timezone
        
        current_date = datetime.now(timezone.utc)
        current_month_start = current_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        from datetime import date as datecls

        last_reset_date = self.get_last_reset_date('monthly')

        if last_reset_date is None:
            return True  # No reset recorded yet

        # Normalize last_reset_date into a datetime
        try:
            if isinstance(last_reset_date, datetime):
                last_reset = last_reset_date
            elif isinstance(last_reset_date, datecls):
                last_reset = datetime(last_reset_date.year, last_reset_date.month, last_reset_date.day, tzinfo=timezone.utc)
            elif isinstance(last_reset_date, str):
                # Try ISO date first, then fallback to YYYY-MM-DD
                try:
                    last_reset = datetime.fromisoformat(last_reset_date)
                except Exception:
                    last_reset = datetime.strptime(last_reset_date, '%Y-%m-%d')
                if last_reset.tzinfo is None:
                    last_reset = last_reset.replace(tzinfo=timezone.utc)
            else:
                # Unknown type - assume reset needed
                return True

            last_reset_month_start = last_reset.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            # If the last reset was in a previous month, we need a new reset
            return last_reset_month_start < current_month_start
        except Exception:
            return True  # On any parse error, assume we need a reset

    def perform_monthly_reset(self, force: bool = False) -> Dict[str, Any]:
        """Perform monthly credit reset for all users
        If force==True, bypass the "already performed this month" check and perform reset anyway.
        """
        from datetime import datetime, timezone
        
        current_date = datetime.now(timezone.utc)
        reset_date = current_date.strftime('%Y-%m-%d')
        
        # Check if reset is needed (unless forced)
        if not force and not self.needs_monthly_reset():
            return {
                'success': False,
                'message': 'Monthly reset not needed - already performed this month',
                'users_affected': 0,
                'total_credits_reset': 0.0
            }
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get default group credits to add to all users
                default_group_row = self.fetch_one("SELECT default_credits FROM credit_groups WHERE id = %s", ('default',))
                default_group_credits = default_group_row['default_credits'] if default_group_row else 100.0
                
                # Get ALL users with their explicit group credits (not including default group)
                if self.db_type == 'postgresql':
                    users_query = """
                        SELECT u.id, u.balance,
                               COALESCE(SUM(CASE WHEN g.id != 'default' THEN g.default_credits ELSE 0 END), 0) as regular_group_credits,
                               STRING_AGG(CASE WHEN g.id != 'default' THEN g.name END, ', ') as group_names
                        FROM credit_users u
                        LEFT JOIN credit_user_groups ug ON u.id = ug.user_id
                        LEFT JOIN credit_groups g ON ug.group_id = g.id
                        GROUP BY u.id, u.balance
                    """
                else:
                    users_query = """
                        SELECT u.id, u.balance,
                               COALESCE(SUM(CASE WHEN g.id != 'default' THEN g.default_credits ELSE 0 END), 0) as regular_group_credits,
                               GROUP_CONCAT(CASE WHEN g.id != 'default' THEN g.name END) as group_names
                        FROM credit_users u
                        LEFT JOIN credit_user_groups ug ON u.id = ug.user_id
                        LEFT JOIN credit_groups g ON ug.group_id = g.id
                        GROUP BY u.id, u.balance
                    """
                
                users_to_reset = self.fetch_all(users_query)
                users_affected = 0
                total_credits_reset = 0.0
                
                # Store pre-reset balances for previous month statistics
                previous_month = current_date.month - 1
                previous_year = current_date.year
                if previous_month <= 0:
                    previous_month = 12
                    previous_year -= 1
                
                for user in users_to_reset:
                    # fetch_all returns dictionaries for both sqlite3.Row (converted with dict(row))
                    # and psycopg2 RealDictCursor. However in some codepaths a sequence/tuple
                    # may still be returned. Handle both shapes robustly.
                    if isinstance(user, dict):
                        user_id = user.get('id') or user.get('user_id')
                        current_balance = user.get('balance', 0.0)
                        # Alias name used in the query
                        regular_group_credits = user.get('regular_group_credits', 0.0)
                        group_names = user.get('group_names') or "No groups"
                    else:
                        # Fallback for sequence/tuple rows (legacy codepaths)
                        user_id = user[0]
                        current_balance = user[1]
                        regular_group_credits = user[2]
                        group_names = user[3] or "No groups"
                    
                    # Calculate total credits: regular group credits + default group credits
                    total_default_credits = regular_group_credits + default_group_credits
                    
                    # Update previous month's statistics with final balance before reset
                    self.execute_query("""
                        UPDATE credit_usage_statistics 
                        SET balance_before_reset = %s
                        WHERE user_id = %s AND year = %s AND month = %s
                    """, (current_balance, user_id, previous_year, previous_month))
                    
                    # Update user balance to sum of all group default credits (including default group)
                    self.execute_query("""
                        UPDATE credit_users 
                        SET balance = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (total_default_credits, user_id))
                    
                    # Record transaction with proper group listing
                    display_groups = "Default Users"
                    if group_names and group_names != "No groups":
                        display_groups = f"Default Users, {group_names}"
                    
                    self.execute_query("""
                        INSERT INTO credit_transactions 
                        (user_id, amount, transaction_type, reason, actor, balance_after)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        user_id,
                        total_default_credits - current_balance,
                        'monthly_reset',
                        f'Monthly reset for groups: {display_groups}',
                        'system',
                        total_default_credits
                    ))
                    
                    users_affected += 1
                    total_credits_reset += total_default_credits
                
                conn.commit()
                
                # Initialize monthly statistics for the new month
                self.initialize_monthly_statistics_for_reset(current_date.year, current_date.month)
                
                # Record the reset event
                reset_id = self.record_reset_event(
                    reset_type='monthly',
                    reset_date=reset_date,
                    users_affected=users_affected,
                    total_credits_reset=total_credits_reset,
                    status='completed',
                    metadata={'reset_timestamp': current_date.isoformat()}
                )
                
                return {
                    'success': True,
                    'message': f'Monthly reset completed for {users_affected} users',
                    'users_affected': users_affected,
                    'total_credits_reset': total_credits_reset,
                    'reset_id': reset_id,
                    'reset_date': reset_date
                }
                
        except Exception as e:
            # Record the failed reset attempt
            self.record_reset_event(
                reset_type='monthly',
                reset_date=reset_date,
                users_affected=0,
                total_credits_reset=0.0,
                status='failed',
                error_message=str(e)
            )
            
            return {
                'success': False,
                'message': f'Monthly reset failed: {str(e)}',
                'users_affected': 0,
                'total_credits_reset': 0.0,
                'error': str(e)
            }

    # Usage statistics methods
    def update_usage_statistics(self, user_id: str, amount: float, model_id: Optional[str] = None):
        """Update monthly usage statistics when credits are deducted"""
        from datetime import datetime, timezone
        
        current_date = datetime.now(timezone.utc)
        year = current_date.year
        month = current_date.month
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get current statistics for this user and month
                row = self.fetch_one("""
                    SELECT credits_used, transactions_count, models_used 
                    FROM credit_usage_statistics 
                    WHERE user_id = %s AND year = %s AND month = %s
                """, (user_id, year, month))
                
                if row:
                    # Update existing record
                    current_credits = row['credits_used']
                    current_transactions = row['transactions_count']
                    models_used_json = row['models_used'] or '[]'
                    
                    try:
                        models_used = json.loads(models_used_json)
                    except json.JSONDecodeError:
                        models_used = []
                    
                    # Add model to list if not already present
                    if model_id and model_id not in models_used:
                        models_used.append(model_id)
                    
                    self.execute_query("""
                        UPDATE credit_usage_statistics 
                        SET credits_used = %s, transactions_count = %s, models_used = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = %s AND year = %s AND month = %s
                    """, (
                        current_credits + amount,
                        current_transactions + 1,
                        json.dumps(models_used),
                        user_id, year, month
                    ))
                else:
                    # Create new record
                    models_used = [model_id] if model_id else []
                    self.execute_query("""
                        INSERT INTO credit_usage_statistics 
                        (user_id, year, month, credits_used, transactions_count, models_used)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (user_id, year, month, amount, 1, json.dumps(models_used)))
                
        except Exception as e:
            # Log error but don't fail the main transaction
            self.log_action(
                log_type="statistics_error",
                actor="system",
                message=f"Failed to update usage statistics for user {user_id}: {str(e)}",
                metadata={"user_id": user_id, "amount": amount, "model_id": model_id}
            )

    def get_user_usage_statistics(self, user_id: str, limit: int = 12) -> List[Dict[str, Any]]:
        """Get user's monthly usage statistics"""
        results = self.fetch_all("""
            SELECT * FROM credit_usage_statistics 
            WHERE user_id = %s 
            ORDER BY year DESC, month DESC 
            LIMIT %s
        """, (user_id, limit))
        
        for result in results:
            if result['models_used']:
                try:
                    result['models_used'] = json.loads(result['models_used'])
                except json.JSONDecodeError:
                    result['models_used'] = []
            else:
                result['models_used'] = []
        return results

    def get_all_usage_statistics(self, year: Optional[int] = None, month: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get usage statistics for all users, optionally filtered by year/month"""
        if year and month:
            results = self.fetch_all("""
                SELECT u.*, cu.balance as current_balance
                FROM credit_usage_statistics u
                LEFT JOIN credit_users cu ON u.user_id = cu.id
                WHERE u.year = %s AND u.month = %s
                ORDER BY u.credits_used DESC
                LIMIT %s
            """, (year, month, limit))
        elif year:
            results = self.fetch_all("""
                SELECT u.*, cu.balance as current_balance
                FROM credit_usage_statistics u
                LEFT JOIN credit_users cu ON u.user_id = cu.id
                WHERE u.year = %s
                ORDER BY u.year DESC, u.month DESC, u.credits_used DESC
                LIMIT %s
            """, (year, limit))
        else:
            results = self.fetch_all("""
                SELECT u.*, cu.balance as current_balance
                FROM credit_usage_statistics u
                LEFT JOIN credit_users cu ON u.user_id = cu.id
                ORDER BY u.year DESC, u.month DESC, u.credits_used DESC
                LIMIT %s
            """, (limit,))
        
        for result in results:
            if result['models_used']:
                try:
                    result['models_used'] = json.loads(result['models_used'])
                except json.JSONDecodeError:
                    result['models_used'] = []
            else:
                result['models_used'] = []
            
            # Get group names for this user
            user_id = result['user_id']
            group_rows = self.fetch_all("""
                SELECT cg.name
                FROM credit_groups cg
                JOIN credit_user_groups cug ON cg.id = cug.group_id
                WHERE cug.user_id = %s
                ORDER BY cg.name
            """, (user_id,))
            
            group_names = [row['name'] for row in group_rows]
            result['group_name'] = ', '.join(group_names) if group_names else 'No groups'
            
        return results

    def get_current_month_pending_usage(self, user_id: str) -> Dict[str, Any]:
        """Get current month's usage for a user (pending/in-progress)"""
        from datetime import datetime, timezone
        
        current_date = datetime.now(timezone.utc)
        year = current_date.year
        month = current_date.month
        
        row = self.fetch_one("""
            SELECT * FROM credit_usage_statistics 
            WHERE user_id = %s AND year = %s AND month = %s
        """, (user_id, year, month))
        
        if row:
            if row['models_used']:
                try:
                    row['models_used'] = json.loads(row['models_used'])
                except json.JSONDecodeError:
                    row['models_used'] = []
            else:
                row['models_used'] = []
            return row
        else:
            return {
                'user_id': user_id,
                'year': year,
                'month': month,
                'credits_used': 0.0,
                'transactions_count': 0,
                'models_used': []
            }

    def get_monthly_usage_summary(self, year: Optional[int] = None, month: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get summary statistics for a specific month"""
        from datetime import datetime, timezone
        
        if not year or not month:
            current_date = datetime.now(timezone.utc)
            year = year or current_date.year
            month = month or current_date.month
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get aggregated statistics
                result = self.fetch_one("""
                    SELECT 
                        COALESCE(SUM(credits_used), 0) as total_credits_used,
                        COALESCE(SUM(transactions_count), 0) as total_transactions,
                        COUNT(DISTINCT user_id) as unique_users,
                        COUNT(*) as total_entries
                    FROM credit_usage_statistics 
                    WHERE year = %s AND month = %s
                """, (year, month))
                
                if result and result["total_entries"] > 0:
                    # Count unique models
                    models_rows = self.fetch_all("""
                        SELECT models_used 
                        FROM credit_usage_statistics 
                        WHERE year = %s AND month = %s AND models_used IS NOT NULL
                    """, (year, month))
                    
                    all_models = set()
                    for row in models_rows:
                        try:
                            models = json.loads(row["models_used"])
                            all_models.update(models)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    
                    summary = dict(result)
                    summary["unique_models"] = len(all_models)
                    return summary
                
                return None
        except Exception as e:
            print(f"Error getting monthly usage summary: {e}")
            return None

    def initialize_monthly_statistics_for_reset(self, year: int, month: int):
        """Initialize statistics for all users when a new month starts (called during reset)"""
        try:
            # Get all users
            users = self.fetch_all("SELECT id FROM credit_users")
            
            created_count = 0
            for user in users:
                user_id = user['id']
                
                # Check if record already exists
                existing = self.fetch_one("""
                    SELECT id FROM credit_usage_statistics 
                    WHERE user_id = %s AND year = %s AND month = %s
                """, (user_id, year, month))
                
                if not existing:
                    # Create new record with zero usage
                    self.execute_query("""
                        INSERT INTO credit_usage_statistics 
                        (user_id, year, month, credits_used, transactions_count, models_used)
                        VALUES (%s, %s, %s, 0.0, 0, '[]')
                    """, (user_id, year, month))
                    created_count += 1
            
            self.log_action(
                log_type="statistics_initialization",
                actor="system",
                message=f"Initialized monthly statistics for {created_count} users for {year}-{month:02d}",
                metadata={"year": year, "month": month, "users_initialized": created_count}
            )
            
        except Exception as e:
            self.log_action(
                log_type="statistics_error",
                actor="system",
                message=f"Failed to initialize monthly statistics: {str(e)}",
                metadata={"year": year, "month": month, "error": str(e)}
            )

    # Waiting list operations
    def add_waiting_list_entry(self, full_name: str, email: str, password_plain: str) -> bool:
        """Insert a new waiting list entry. Returns False if email already exists.
        Stores plaintext password (per user request). This is insecure — be sure you understand the risk.
        """
        try:
            # Use appropriate placeholder normalization
            if self.db_type == 'postgresql':
                self.execute_query("""
                    INSERT INTO credit_waiting_list (full_name, email, password_plain)
                    VALUES (%s, %s, %s)
                """, (full_name, email, password_plain))
            else:
                # SQLite placeholder differences handled by execute_query
                self.execute_query("""
                    INSERT INTO credit_waiting_list (full_name, email, password_plain)
                    VALUES (%s, %s, %s)
                """, (full_name, email, password_plain))
            return True
        except Exception as e:
            # Likely UNIQUE constraint on email
            try:
                self.log_action('waiting_list_error', 'system', f'Failed to add waiting list entry: {e}')
            except Exception:
                pass
            return False

    def mark_waiting_list_processed(self, entry_id: int) -> Optional[Dict[str, Any]]:
        """Mark a waiting list entry as processed and set processed_at timestamp. Returns the updated row or None."""
        try:
            # Update the row
            if self.db_type == 'postgresql':
                self.execute_query(
                    "UPDATE credit_waiting_list SET processed = %s, processed_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (True, entry_id)
                )
            else:
                # SQLite uses integers for booleans
                self.execute_query(
                    "UPDATE credit_waiting_list SET processed = ?, processed_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (1, entry_id)
                )

            # Return the updated row
            row = self.fetch_one(
                "SELECT id, full_name, email, created_at, processed, processed_at FROM credit_waiting_list WHERE id = %s",
                (entry_id,)
            )
            return row
        except Exception as e:
            try:
                self.log_action('waiting_list_error', 'system', f'Failed to mark processed for id {entry_id}: {e}')
            except Exception:
                pass
            return None

    def list_waiting_list_entries(self, limit: int = 100, offset: int = 0) -> list:
        """Return waiting list entries ordered with unprocessed first, then by created_at desc"""
        rows = self.fetch_all("""
            SELECT id, full_name, email, created_at, processed, processed_at
            FROM credit_waiting_list
            ORDER BY processed ASC, created_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))
        return rows

# Global database instance
db = CreditDatabase()
