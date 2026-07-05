from __future__ import annotations

import re
from typing import Any

from app.llm.base import LLMProvider


ACTION_HINTS = [
    "analyser",
    "vérifier",
    "valider",
    "contrôler",
    "préparer",
    "transmettre",
    "suivre",
    "mettre à jour",
    "identifier",
    "traiter",
]


class HeuristicProvider(LLMProvider):
    async def analyze_document(
        self,
        *,
        title: str,
        content_text: str,
        existing_nodes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        sections = self._sections(content_text)
        cards = [self._card_for_section(title, section, existing_nodes) for section in sections[:6]]
        return {
            "document_summary": f"Analyse de secours générée localement pour {title}.",
            "cards": cards,
            "orphans": [],
            "warnings": [
                "Analyse heuristique utilisée : démarre Ollama pour une extraction plus intelligente."
            ],
        }

    def _sections(self, text: str) -> list[str]:
        normalized = re.sub(r"\r\n?", "\n", text).strip()
        heading_chunks = re.split(r"\n(?=#{1,3}\s+|\d+[\).\s-])", normalized)
        chunks = [chunk.strip() for chunk in heading_chunks if len(chunk.strip()) > 60]
        if chunks:
            return chunks
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", normalized) if len(p.strip()) > 60]
        return paragraphs or [normalized[:1800]]

    def _card_for_section(
        self, title: str, section: str, existing_nodes: list[dict[str, Any]]
    ) -> dict[str, Any]:
        sentences = re.split(r"(?<=[.!?])\s+", section)
        first_sentence = (sentences[0] if sentences else section).strip()
        words = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'-]{3,}", section)
        unique_words = []
        for word in words:
            cleaned = word.strip(".,;:").lower()
            if cleaned not in unique_words and cleaned not in {"dans", "avec", "pour", "plus", "cette"}:
                unique_words.append(cleaned)
        theme = self._theme(first_sentence, title)
        actions = [hint for hint in ACTION_HINTS if hint in section.lower()][:5]
        if not actions:
            actions = ["identifier", "structurer"]
        objects = [word.capitalize() for word in unique_words[:6]]
        tasks = [s.strip()[:140] for s in sentences[1:4] if len(s.strip()) > 20]
        if not tasks:
            tasks = [first_sentence[:140]]
        suggested_links = self._links(theme, existing_nodes)
        return {
            "theme_label": theme,
            "main_effect": {
                "label": self._effect_label(first_sentence, theme),
                "description": first_sentence[:320],
                "level": "operational",
                "confidence": "medium",
            },
            "objects": objects,
            "actions": actions,
            "conditions": self._conditions(section),
            "tasks": tasks,
            "secondary_effects": [],
            "suggested_links": suggested_links,
            "source_excerpt": section[:700],
            "confidence": "medium",
        }

    def _theme(self, first_sentence: str, fallback: str) -> str:
        heading = re.sub(r"^#+\s*", "", first_sentence).split("\n", 1)[0].strip()
        heading = re.sub(r"^\d+[\).\s-]+", "", heading)
        return (heading[:70] or fallback or "Thème détecté").strip()

    def _effect_label(self, first_sentence: str, theme: str) -> str:
        cleaned = re.sub(r"^#+\s*", "", first_sentence).strip()
        if len(cleaned) < 18:
            return f"Clarifier {theme}"
        return cleaned[:110]

    def _conditions(self, section: str) -> list[str]:
        matches = re.findall(
            r"(?:si|lorsque|quand|en cas de|à condition que)\s+([^.;\n]{8,120})",
            section,
            flags=re.IGNORECASE,
        )
        return [match.strip() for match in matches[:4]]

    def _links(self, theme: str, existing_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        theme_words = set(re.findall(r"\w{4,}", theme.lower()))
        links = []
        for node in existing_nodes:
            label_words = set(re.findall(r"\w{4,}", str(node.get("label", "")).lower()))
            if theme_words and theme_words.intersection(label_words):
                links.append(
                    {
                        "source_label": theme,
                        "target_existing_node_id": node["id"],
                        "target_label": node["label"],
                        "relation_type": "proche de",
                        "confidence": "medium",
                        "reason": "Vocabulaire proche détecté dans les libellés.",
                    }
                )
            if len(links) >= 3:
                break
        return links
