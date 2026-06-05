# Section 4 — Vector / RAG Design

> 負責人：蔣耀德 | 配分：/15

## 4.1 Embedding 對象與 Cosine Similarity

<!-- 說明什麼資料被 embed（policy documents）、為何選用 cosine similarity -->
<!-- 要求：解釋 cosine similarity 是 magnitude-independent、測量 embedding space 中的方向相似度 -->
<!-- 不能只說「it measures how similar two things are」 -->

## 4.2 RAG Pipeline

<!-- 完整描述四個階段：query embedding → similarity search → retrieved documents → LLM prompt → answer -->
<!-- 要求：每個階段有足夠細節，讀者可以依此實作 -->

## 4.3 Embedding Dimension 與 Provider 切換

<!-- 說明實作使用的 dimension（Ollama: 768 / Gemini: 3072） -->
<!-- 說明 seeding 後切換 provider 會造成 dimension mismatch，使 index 無法使用 -->
