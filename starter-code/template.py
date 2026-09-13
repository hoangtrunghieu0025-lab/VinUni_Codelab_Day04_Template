"""
Lab #4: System Prompt Engineering & Tool Calling Engine
Học viên hoàn thiện các mục TODO để hoàn thành bài lab.

Kiến trúc:
  - ChatbotBaseline: LLM thuần, không dùng tool → quan sát hallucination.
  - ToolCallingAgent: Agent dùng System Prompt + 2 Tool Schemas.
"""

import json
import re
from typing import Dict, Any, List
from tools import TOOL_DEFINITIONS, TOOL_MAP, search_product_catalog, submit_support_ticket

# ═══════════════════════════════════════════════════════════════════════════
# TODO 1: Thiết kế SYSTEM PROMPT cấp sản xuất
# Yêu cầu: Phải chứa Persona, Core Rules, Operational Boundaries, Output Contract.
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
# TODO: Viết System Prompt cho VinAssistant
# Gợi ý các phần cần có:
# 1. PERSONA: Tên, vai trò, giọng nói
# 2. AVAILABLE TOOLS: Liệt kê {tools}
# 3. CORE RULES: Không bịa dữ liệu, bắt buộc gọi tool khi cần
# 4. OPERATIONAL BOUNDARIES: Chỉ trả lời về Vingroup
# 5. OUTPUT CONTRACT: Format trả lời (Thought/Action/Observation/Final Answer)
Bạn là VinAssistant, trợ lý AI chuyên nghiệp và thân thiện của hệ sinh thái Vingroup.

## PERSONA
- Tư vấn sản phẩm VinFast và dịch vụ Vinpearl bằng tiếng Việt rõ ràng, chính xác.

## AVAILABLE TOOLS
- search_product_catalog: tra cứu sản phẩm theo danh mục và giá tối đa.
- submit_support_ticket: tạo yêu cầu hỗ trợ cho khách hàng.

## CORE RULES
- Không bịa giá, sản phẩm, tình trạng hoặc mã ticket.
- Bắt buộc dùng tool khi câu hỏi cần dữ liệu catalog hoặc cần tạo ticket.
- Chỉ khẳng định thông tin có trong dữ liệu hoặc kết quả tool.

## OPERATIONAL BOUNDARIES
- Chỉ hỗ trợ sản phẩm và dịch vụ thuộc Vingroup, đặc biệt VinFast và Vinpearl.
- Từ chối lịch sự các yêu cầu ngoài phạm vi.

## OUTPUT CONTRACT
- Ghi nhận Thought, Action, Observation trong trace nội bộ.
- Final Answer phải ngắn gọn, tiếng Việt, nêu rõ kết quả hoặc lý do không thể xử lý.
"""


# ═══════════════════════════════════════════════════════════════════════════
# CLASS: ChatbotBaseline
# ═══════════════════════════════════════════════════════════════════════════

class ChatbotBaseline:
    """Baseline LLM Chatbot — Không sử dụng Tool Calling hay ReAct Loop."""

    def query(self, user_input: str) -> Dict[str, Any]:
        # TODO 2: Trả về câu trả lời tĩnh (mock) hoặc gọi Gemini API 1 lượt (không dùng tool)
        # Mục tiêu: Quan sát hiện tượng bịa thông tin (hallucination)
        return {
            "answer": f"[Chatbot Baseline] Trả lời cho: {user_input}",
            "tool_calls": [],
            "status": "success",
            "mode": "mock_baseline"
        }


# ═══════════════════════════════════════════════════════════════════════════
# CLASS: ToolCallingAgent
# ═══════════════════════════════════════════════════════════════════════════

class ToolCallingAgent:
    """Agent với System Prompt Engineering & Tool Calling."""

    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        self.trace: List[Dict[str, Any]] = []

    def run(self, user_input: str) -> Dict[str, Any]:
        """Điểm vào chính — chạy Agent Loop."""
        self.trace = []

        # TODO 3: Phân tích intent từ user_input
        #   - Xác định cần gọi tool nào (catalog? ticket? cả hai? FAQ?)
        #   - Gợi ý: Dùng keyword matching hoặc regex
        normalized_input = user_input.lower()
        needs_catalog = any(keyword in normalized_input for keyword in (
            "xe điện", "vinfast", "du lịch", "vinpearl", "sản phẩm", "giá"
        )) and not any(keyword in normalized_input for keyword in (
            "bảo hành", "bị lỗi", "hỏng", "sự cố", "hỗ trợ"
        ))
        needs_ticket = any(keyword in normalized_input for keyword in (
            "bị lỗi", "hỏng", "sự cố", "khiếu nại", "hỗ trợ", "gấp"
        ))
        is_battery_faq = "bảo hành" in normalized_input and "pin" in normalized_input

        category = "xe_dien" if any(keyword in normalized_input for keyword in (
            "xe điện", "vinfast"
        )) else "du_lich"
        price_match = re.search(
            r"(?:dưới|đến|tối đa|không quá)\s*([\d.,]+)\s*(triệu|tỷ|tỉ|đồng)?",
            normalized_input
        )
        max_price = 999999999999
        if price_match:
            amount = float(price_match.group(1).replace(".", "").replace(",", "."))
            unit = price_match.group(2) or "đồng"
            multiplier = {"triệu": 1_000_000, "tỷ": 1_000_000_000, "tỉ": 1_000_000_000, "đồng": 1}[unit]
            max_price = int(amount * multiplier)

        customer_match = re.search(r"tôi tên\s+([^,.!?]+)", user_input, re.IGNORECASE)
        customer_name = customer_match.group(1).strip() if customer_match else "Khách hàng"
        priority = "high" if any(keyword in normalized_input for keyword in (
            "nghiêm trọng", "gấp", "khẩn cấp"
        )) else "medium"

        # TODO 4: Xây dựng Agent Loop (while iteration <= self.max_iterations)
        #   - Iteration 1: Gọi tool #1 nếu cần (search_product_catalog)
        #   - Iteration 2: Gọi tool #2 nếu cần (submit_support_ticket)
        #   - Iteration 3+: Tổng hợp Final Answer từ trace
        #   - Lưu mỗi bước vào self.trace

        self.trace.append({"step": "init", "user_input": user_input})
        self.trace.append({
            "step": "intent_detection",
            "needs_catalog": needs_catalog,
            "needs_ticket": needs_ticket,
            "is_faq": is_battery_faq
        })

        if is_battery_faq:
            answer = "Theo thông tin sản phẩm VinFast, pin xe điện được bảo hành 10 năm."
            self.trace.append({"step": "final_answer", "answer": answer})
            return {"answer": answer, "trace": self.trace, "iterations": 1, "status": "completed"}

        if not needs_catalog and not needs_ticket:
            answer = "Tôi chỉ có thể hỗ trợ các sản phẩm và dịch vụ thuộc hệ sinh thái Vingroup."
            self.trace.append({"step": "final_answer", "answer": answer})
            return {"answer": answer, "trace": self.trace, "iterations": 1, "status": "completed"}

        planned_calls = []
        if needs_catalog:
            planned_calls.append((
                "search_product_catalog",
                {"category": category, "max_price": max_price}
            ))
        if needs_ticket:
            planned_calls.append((
                "submit_support_ticket",
                {
                    "customer_name": customer_name,
                    "issue_description": user_input,
                    "priority": priority
                }
            ))

        observations = {}
        iteration = 0
        while planned_calls and iteration < self.max_iterations:
            tool_name, arguments = planned_calls.pop(0)
            iteration += 1
            result = TOOL_MAP[tool_name](**arguments)
            observations[tool_name] = result
            self.trace.append({
                "step": "tool_call",
                "iteration": iteration,
                "tool": tool_name,
                "arguments": arguments,
                "observation": result
            })

        if planned_calls:
            answer = "Lỗi: Vượt quá số bước tối đa."
            status = "max_iterations_reached"
        elif "submit_support_ticket" in observations:
            ticket = observations["submit_support_ticket"]
            answer = f"Đã tạo ticket {ticket['ticket_id']} cho {ticket['customer_name']} với mức ưu tiên {ticket['priority']}."
            if "search_product_catalog" in observations:
                answer += " " + self._format_catalog_answer(observations["search_product_catalog"])
            status = "completed"
        else:
            answer = self._format_catalog_answer(observations["search_product_catalog"])
            status = "completed"

        self.trace.append({"step": "final_answer", "answer": answer})
        return {
            "answer": answer,
            "trace": self.trace,
            "iterations": iteration,
            "status": status
        }

    @staticmethod
    def _format_catalog_answer(results: List[Dict[str, Any]]) -> str:
        if not results or "error" in results[0]:
            return "Rất tiếc, không tìm thấy sản phẩm phù hợp."
        products = "; ".join(
            f"{product['name']} ({product['price_vnd']:,} VNĐ)"
            for product in results
        )
        return f"Các sản phẩm phù hợp: {products}."


# ═══════════════════════════════════════════════════════════════════════════
# MAIN — Chạy thử nhanh
# ═══════════════════════════════════════════════════════════════════════════

def main():
    user_query = "Tôi muốn xem xe điện VinFast giá dưới 600 triệu."

    print("=== RUNNING CHATBOT BASELINE ===")
    chatbot = ChatbotBaseline()
    print(chatbot.query(user_query))

    print("\n=== RUNNING TOOL CALLING AGENT ===")
    agent = ToolCallingAgent(max_iterations=5)
    result = agent.run(user_query)
    print("Result:", result["answer"])
    print("Trace Log:", json.dumps(agent.trace, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
