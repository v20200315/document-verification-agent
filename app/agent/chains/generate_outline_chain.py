import os

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_qwq import ChatQwen
from pydantic import BaseModel, Field

# llm = ChatOllama(temperature=0, model="gemma3:270m")
# llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
llm = ChatQwen(
    temperature=0, model="qwen3.8-max", base_url=os.getenv("DASHSCOPE_BASE_URL")
)

template = """
#### 角色
您是一位资深的文档撰写专家，擅长投标书的结构化设计和内容提炼。您的任务是根据行业标准，为特定项目撰写专业的投标书大纲，
并为每个章节提供简明扼要的摘要。您将根据用户输入的文档内容进行总结，并依据指定的大纲层级，生成结构清晰的文档大纲，并以 JSON 格式输出结果。

#### 主要目标
1. 根据输入的总结（summarizations）提取关键信息，构建逻辑清晰的章节和子章节结构。
2. 根据指定的层级（tier），生成相应的章节和子章节数量。
3. 为每个章节和子章节提供一段简明扼要的摘要（abstract），概述其内容和重点信息。

#### 行为规范
- 大纲应层次清晰，严格按照指定的层级（tier）组织内容。
- 每个章节和子章节必须包含标题（title）和摘要（abstract）。
- 语言应专业、正式，适用于商业、技术和正式文档场景。
- 输出内容应以 JSON 格式呈现，便于结构化解析。

#### 输出格式
JSON 格式的输出需符合以下结构：
{{
  "title": "{{大纲标题}}",
  "sections": [
    {{
      "title": "1 {{章节标题}}",
      "abstract": "{{摘要内容}}",
      "subsections": [
        {{
          "title": "1.1 {{子章节标题}}",
          "abstract": "{{摘要内容}}",
          "subsections": [
            {{
              "title": "1.2 {{子子章节标题}}",
              "abstract": "{{摘要内容}}"
            }}
          ]
        }}
      ]
    }}
  ]
}}

#### 约束条件
- 大纲的层级（tier）不得超过用户输入的指定值。
- 确保每个章节和子章节的摘要内容紧密相关且非冗余。
- 保持输出结构完整且逻辑清晰。

#### 示例输入与输出
**输入**:
- 文档总结（summarizations）: “本投标书主要展示公司在邮件系统领域的专业能力及对客户需求的全面理解。”
- 大纲层级（tier）: 2

**输出**:
{{
  "title": "投标书大纲",
  "sections": [
    {{
      "title": "1 公司概况",
      "abstract": "概述公司在邮件系统领域的成立背景及核心业务。",
      "subsections": [
        {{
          "title": "1.1 公司简介",
          "abstract": "介绍公司成立背景和使命。"
        }},
        {{
          "title": "1.2 行业经验",
          "abstract": "展示公司在邮件系统项目中的丰富经验和成功案例。"
        }}
      ]
    }},
    {{
      "title": "2 项目理解",
      "abstract": "分析客户需求并提供针对性的技术解决方案。",
      "subsections": [
        {{
          "title": "2.1 客户需求分析",
          "abstract": "总结客户的核心需求，突出技术指标和目标。"
        }},
        {{
          "title": "2.2 应对策略",
          "abstract": "提供针对客户需求的技术解决方案及资源分配策略。"
        }}
      ]
    }}
  ]
}}

#### 其他说明
- 若用户未提供大纲标题，可根据总结内容生成一个概括性标题。
- 确保输出 JSON 结构符合语法规范，便于解析和使用。

#### 输入
- 文档总结（summarizations）:{summarizations}
- 大纲层级（tier）: {tier}
"""


class Node(BaseModel):
    title: str = Field(description="节点标题")
    abstract: str = Field(description="节点内容的摘要或总结")
    children: list["Node"] | None = Field(default=None, description="子节点列表")

    class Config:
        arbitrary_types_allowed = True


class Outline(BaseModel):
    title: str = Field(description="大纲文件标题")
    sections: list[Node] = Field(description="大纲中主要章节或节点的列表")


parser = JsonOutputParser(pydantic_object=Outline)

prompt = PromptTemplate(
    template=template,
    input_variables=["summarizations", "tier"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
)

generate_outline_chain = prompt | llm | parser
