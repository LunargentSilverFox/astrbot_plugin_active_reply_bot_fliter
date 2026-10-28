from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("active_reply_bot_fliter", "LunargentSilverFox", "用于主动回复的机器人，过滤指定关键词（双向）,并且询问机器人是否保持沉默或者回答.（不支持流式输出）", "1.0.0")
class active_reply_bot_fliter(Star):
    
    fliter_word_bot = ["[沉默]","[silent]"]#机器人发出的消息中包含该词则视为机器人不回复
    fliter_word_client = ["[图片]","[表情]"]#用户发送的消息中包含该词则被过滤（机器人看不到）

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
        '''检查是否包含过滤词,如果包含则直接结束一次与bot会话的流程'''
        message = event.get_message_str()
        if any(word in message for word in self.fliter_word_client):
            event.stop_event()

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