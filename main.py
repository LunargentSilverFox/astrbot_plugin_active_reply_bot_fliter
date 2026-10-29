from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import (
    Face,
    File,
    Forward,
    Image,
    Record,
    Video,
)

@register("active_reply_bot_fliter", "LunargentSilverFox", "用于主动回复的机器人，过滤指定关键词（双向）,并且询问机器人是否保持沉默或者回答.（不支持流式输出）", "1.0.0")
class active_reply_bot_fliter(Star):
    
    fliter_word_bot = ["[沉默]","[silent]"]#机器人发出的消息中包含该词则视为机器人不回复
    fliter_word_client = []
    # 媒体消息的文本占位符（图片；语音/视频/文件/转发用组件类型判断）
    media_message_markers = ("[图片]",)
    # 表情的文本占位符。用 [表情 作为前缀，可同时匹配 [表情] 与 QQ 官方解析出的 [表情:xxx]
    face_message_markers = ("[表情",)
    # 需要拦截的媒体消息组件（图片/语音/视频/文件/转发，不含表情）。
    # 用 isinstance 判断组件类型，比比较 comp.type 字段更可靠：
    # comp.type 在部分场景下会被序列化成小写字符串，导致与 ComponentType 枚举比较失败而漏拦截。
    media_component_classes = (Image, Record, Video, File, Forward)
    # 表情组件（QQ 官方等平台的表情是文本，用 face_message_markers 匹配）
    face_component_classes = (Face,)

    con = "你需要检查消息是否和你有关，可能是其他用户之间的交流。如果无关，则只回复{bot_filter_words}中的任意一个词。"

    def __init__(self, context: Context, config: dict | None = None) -> None:
        super().__init__(context)
        logger.info("主动bot已启动")
        config = config or {}
        self.fliter_word_bot = self._get_filter_words(
            config,
            "bot_filter_words",
            type(self).fliter_word_bot,
        )
        self.fliter_word_client = self._get_filter_words(
            config,
            "client_filter_words",
            type(self).fliter_word_client,
        )
        self.filter_media_messages = config.get("filter_media_messages", True)
        if not isinstance(self.filter_media_messages, bool):
            logger.warning("配置项 filter_media_messages 必须是布尔值，使用默认值 True。")
            self.filter_media_messages = True
        self.filter_face_messages = config.get("filter_face_messages", True)
        if not isinstance(self.filter_face_messages, bool):
            logger.warning("配置项 filter_face_messages 必须是布尔值，使用默认值 True。")
            self.filter_face_messages = True
        prompt_suffix = config.get("system_prompt_suffix", type(self).con)
        if not isinstance(prompt_suffix, str):
            logger.warning("配置项 system_prompt_suffix 必须是文本，使用默认值。")
            prompt_suffix = type(self).con
        self.con = prompt_suffix.replace(
            "{bot_filter_words}",
            "、".join(self.fliter_word_bot),
        )

    @staticmethod
    def _get_filter_words(
        config: dict,
        key: str,
        defaults: list[str],
    ) -> list[str]:
        words = config.get(key, defaults)
        if not isinstance(words, list):
            logger.warning(f"配置项 {key} 必须是关键词列表，使用默认值。")
            return defaults.copy()

        if any(not isinstance(word, str) for word in words):
            logger.warning(f"配置项 {key} 中的非文本关键词已忽略。")
        return [
            word.strip()
            for word in words
            if isinstance(word, str) and word.strip()
        ]

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def check_client_msg(self, event: AstrMessageEvent) -> None:
        '''检查是否包含过滤词/媒体/表情，如果包含则直接结束一次与bot会话的流程'''
        message = event.get_message_str()
        outline = event.get_message_outline()
        comps = event.get_messages()

        # 媒体消息（图片/语音/视频/文件/转发）。
        # 媒体组件不会出现在纯文本里，必须检查消息链里的组件类型；
        # 纯图片时 get_message_str() 为空，outline 才会出现 [图片]。
        contains_media = any(
            isinstance(comp, self.media_component_classes) for comp in comps
        ) or any(marker in outline for marker in self.media_message_markers)

        # 表情消息（Face 组件，或 QQ 官方等平台解析出的 [表情:xxx] 文本）
        contains_face = any(
            isinstance(comp, self.face_component_classes) for comp in comps
        ) or any(marker in outline for marker in self.face_message_markers)

        contains_custom_filter_word = any(
            word in message
            for word in self.fliter_word_client
            if word not in self.media_message_markers
            and word not in self.face_message_markers
        )

        if (
            (self.filter_media_messages and contains_media)
            or (self.filter_face_messages and contains_face)
            or contains_custom_filter_word
        ):
            event.stop_event()
            logger.info(f"已拦截媒体/表情/过滤消息：{outline}")

    @filter.on_llm_request()
    async def append_system_prompt(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
    ) -> None:
        '''将可配置的指令追加到系统提示词末尾'''
        if event.is_stopped() or not self.con.strip():
            return

        if req.system_prompt.strip():
            req.system_prompt = f"{req.system_prompt.rstrip()}\n\n{self.con}"
        else:
            req.system_prompt = self.con

    @filter.on_decorating_result()
    async def check_bot_msg(self, event: AstrMessageEvent) -> None:
        '''检查是否包含过滤词，如果包含则截断并控制台打印：bot不回复'''
        result = event.get_result()
        if result is None or not result.is_llm_result():
            return

        message = result.get_plain_text()
        for word in self.fliter_word_bot:
            if word in message:
                result.chain.clear()
                logger.info(f"bot不回复：回复包含过滤词 {word}")
                return
