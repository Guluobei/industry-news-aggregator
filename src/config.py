"""行业新闻聚合推送器 - 配置解析与校验模块"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


def resolve_env(value: str) -> str:
    """将 ${VAR_NAME} 格式的占位符替换为环境变量值"""
    if not isinstance(value, str):
        return value
    return re.sub(
        r"\$\{(\w+)\}",
        lambda m: os.environ.get(m.group(1), ""),
        value,
    )


def _resolve_dict(d: dict) -> dict:
    """递归解析字典中所有字符串的环境变量占位符"""
    result = {}
    for k, v in d.items():
        if isinstance(v, str):
            result[k] = resolve_env(v)
        elif isinstance(v, dict):
            result[k] = _resolve_dict(v)
        elif isinstance(v, list):
            result[k] = [
                resolve_env(item) if isinstance(item, str) else _resolve_dict(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            result[k] = v
    return result


class FilterConfig(BaseModel):
    """筛选规则配置"""
    industry: str = ""
    keywords: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    top_n: int = 10
    hours: int = 168

    @field_validator("top_n")
    @classmethod
    def validate_top_n(cls, v: int) -> int:
        if v < 1 or v > 50:
            raise ValueError("top_n 必须在 1-50 之间")
        return v

    @field_validator("hours")
    @classmethod
    def validate_hours(cls, v: int) -> int:
        if v < 1 or v > 720:
            raise ValueError("hours 必须在 1-720 之间（最多30天）")
        return v


class FeishuPushConfig(BaseModel):
    """飞书推送配置"""
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    doc_folder: str = ""
    notify_chat: str = ""


class EmailPushConfig(BaseModel):
    """邮箱推送配置"""
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    to: list[str] = Field(default_factory=list)


class LocalPushConfig(BaseModel):
    """本地文件推送配置"""
    enabled: bool = False
    path: str = "./output"
    format: str = "markdown"


class PushConfig(BaseModel):
    """推送渠道总配置"""
    feishu: FeishuPushConfig = Field(default_factory=FeishuPushConfig)
    email: EmailPushConfig = Field(default_factory=EmailPushConfig)
    local: LocalPushConfig = Field(default_factory=LocalPushConfig)


class ContentConfig(BaseModel):
    """内容生成配置"""
    summary_mode: str = "extract"
    summary_max_length: int = 300
    insight_enabled: bool = False
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"


class AppConfig(BaseModel):
    """应用总配置"""
    sources: list[str] = Field(default_factory=list)
    filter: FilterConfig = Field(default_factory=FilterConfig)
    push: PushConfig = Field(default_factory=PushConfig)
    rsshub_url: str = "http://localhost:1200"
    content: ContentConfig = Field(default_factory=ContentConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AppConfig":
        """从YAML文件加载配置，自动解析环境变量"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")

        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not raw:
            raise ValueError("配置文件为空")

        # 解析环境变量占位符
        resolved = _resolve_dict(raw)

        # 从环境变量补充凭证
        if "push" in resolved and "feishu" in resolved["push"]:
            feishu = resolved["push"]["feishu"]
            if not feishu.get("app_id"):
                feishu["app_id"] = os.environ.get("FEISHU_APP_ID", "")
            if not feishu.get("app_secret"):
                feishu["app_secret"] = os.environ.get("FEISHU_APP_SECRET", "")

        if "push" in resolved and "email" in resolved["push"]:
            email = resolved["push"]["email"]
            if not email.get("smtp_user"):
                email["smtp_user"] = os.environ.get("EMAIL_USER", "")
            if not email.get("smtp_password"):
                email["smtp_password"] = os.environ.get("EMAIL_PASSWORD", "")

        return cls.model_validate(resolved)

    def validate_push_channels(self) -> list[str]:
        """校验至少有一个推送渠道可用，返回可用渠道列表"""
        available = []
        if self.push.feishu.enabled:
            if not self.push.feishu.app_id or not self.push.feishu.app_secret:
                raise ValueError(
                    "飞书推送已启用，但缺少凭证。请设置环境变量 FEISHU_APP_ID 和 FEISHU_APP_SECRET"
                )
            available.append("feishu")
        if self.push.email.enabled:
            if not self.push.email.smtp_user or not self.push.email.smtp_password:
                raise ValueError(
                    "邮箱推送已启用，但缺少凭证。请设置环境变量 EMAIL_USER 和 EMAIL_PASSWORD"
                )
            available.append("email")
        if self.push.local.enabled:
            available.append("local")
        if not available:
            raise ValueError("未启用任何推送渠道，请在配置中至少启用一个")
        return available
