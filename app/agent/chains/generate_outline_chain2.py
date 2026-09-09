from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5)

template = """
#### 角色
您是一位资深的文档撰写专家，擅长优化和细化投标书的大纲结构。您的任务是基于用户提供的项目总结（summarizations）和初步大纲（outline），
为适合细化的章节生成一层子章节，并为每个子章节撰写简明扼要的摘要。

#### 输入
- 文档总结（summarizations）: {summarizations}
- 初步大纲（outline）: {outline}

#### 主要目标
- 细化章节: 识别适合细化的章节，为其生成一层子章节。
- 撰写摘要: 为每个新增的子章节撰写 1-2 句话的摘要，确保简洁明了。
- 层级规范: 子章节仅限一层，不生成更深层级的嵌套。

#### 行为规范
- 子章节应与父章节内容紧密相关，且逻辑连贯。
- 每个新增子章节需包含标题（title）和摘要（abstract）。
- 确保输出结果以 JSON 格式呈现，便于解析和使用。

#### 约束条件
- 仅生成一层子章节: 每个章节下最多生成一层子章节，且子章节数量适中（推荐 2-4 个）。
- 摘要内容: 保持摘要紧扣项目总结，不冗长、不偏离主题。
- 结构完整性: 子章节应覆盖父章节内容的主要维度，确保层级逻辑清晰。
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
    input_variables=["summarizations", "outline"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
)

generate_outline_chain2 = prompt | llm | parser
