from brainyflow import Node, Memory # Import Memory
import yaml
from utils import call_llm

class ChainOfThoughtNode(Node):
    async def prep(self, memory: Memory):
        # Gather problem and previous thoughts
        problem = memory.problem if hasattr(memory, 'problem') else ""
        thoughts = memory.thoughts if hasattr(memory, 'thoughts') else []
        current_thought_number = memory.current_thought_number if hasattr(memory, 'current_thought_number') else 0
        # Increment the current thought number in memory
        memory.current_thought_number = current_thought_number + 1
        total_thoughts_estimate = memory.total_thoughts_estimate if hasattr(memory, 'total_thoughts_estimate') else 5

        # Format previous thoughts
        thoughts_text = "\n".join([
            f"Thought {t['thought_number']}: {t['content']}" +
            (f" (Revision of Thought {t['revises_thought']})" if t.get('is_revision') and t.get('revises_thought') else "") +
            (f" (Branch from Thought {t['branch_from_thought']}, Branch ID: {t['branch_id']})"
             if t.get('branch_from_thought') else "")
            for t in thoughts
        ])

        return {
            "problem": problem,
            "thoughts_text": thoughts_text,
            "thoughts": thoughts,
            "current_thought_number": current_thought_number + 1,
            "total_thoughts_estimate": total_thoughts_estimate
        }

    async def exec(self, prep_res):
        problem = prep_res["problem"]
        thoughts_text = prep_res["thoughts_text"]
        current_thought_number = prep_res["current_thought_number"]
        total_thoughts_estimate = prep_res["total_thoughts_estimate"]

        # Create the prompt for the LLM
        prompt = f"""
You are solving a hard problem using Chain of Thought reasoning. Think step-by-step.

Problem: {problem}

Previous thoughts:
{thoughts_text if thoughts_text else "No previous thoughts yet."}

Please generate the next thought (Thought {current_thought_number}). You can:
1. Continue with the next logical step
2. Revise a previous thought if needed
3. Branch into a new line of thinking
4. Generate a hypothesis if you have enough information
5. Verify a hypothesis against your reasoning
6. Provide a final solution if you've reached a conclusion

Current thought number: {current_thought_number}
Current estimate of total thoughts needed: {total_thoughts_estimate}

Format your response as a YAML structure with these fields:
- content: Your thought content
- next_thought_needed: true/false (true if more thinking is needed)
- is_revision: true/false (true if revising a previous thought)
- revises_thought: null or number (if is_revision is true)
- branch_from_thought: null or number (if branching from previous thought)
- branch_id: null or string (a short identifier for this branch)
- total_thoughts: number (your updated estimate if changed)

Only set next_thought_needed to false when you have a complete solution and the content explains the solution.
Output in YAML format:
```yaml
content: |
  # If you have a complete solution, explain the solution here.
  # If it's a revision, provide the updated thought here.
  # If it's a branch, provide the new thought here.
next_thought_needed: true/false
is_revision: true/false
revises_thought: null or number
branch_from_thought: null or number
branch_id: null or string
total_thoughts: number
```"""
        
        response = call_llm(prompt)
        yaml_str = response.split("```yaml")[1].split("```")[0].strip()
        thought_data = yaml.safe_load(yaml_str)
        
        # Add thought number
        thought_data["thought_number"] = current_thought_number
        return thought_data


    async def post(self, memory: Memory, prep_res, exec_res):
        # Add the new thought to the list
        if not hasattr(memory, 'thoughts') or not isinstance(memory.thoughts, list):
            memory.thoughts = []

        memory.thoughts.append(exec_res)

        # Update total_thoughts_estimate if changed
        if "total_thoughts" in exec_res and exec_res["total_thoughts"] != (memory.total_thoughts_estimate if hasattr(memory, 'total_thoughts_estimate') else 5):
            memory.total_thoughts_estimate = exec_res["total_thoughts"]

        # If we're done, extract the solution from the last thought
        if exec_res.get("next_thought_needed", True) == False:
            memory.solution = exec_res.get("content", "No solution provided")
            print("\n=== FINAL SOLUTION ===")
            print(memory.solution)
            print("======================\n")
            self.trigger("end")
            return

        # Otherwise, continue the chain
        print(f"\n{exec_res.get('content', 'No content provided')}")
        print(f"Next thought needed: {exec_res.get('next_thought_needed', True)}")
        print(f"Total thoughts estimate: {memory.total_thoughts_estimate if hasattr(memory, 'total_thoughts_estimate') else 5}")
        print("-" * 50)

        self.trigger("continue")
