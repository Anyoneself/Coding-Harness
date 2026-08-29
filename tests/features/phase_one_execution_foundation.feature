Feature: Turn 脱离客户端连接后仍可可靠执行

  Scenario: SSE 断开后事件可完整重放
    Given 一个会在后台完成的只读 Turn
    When 客户端在执行期间不保持事件连接
    Then Turn 最终状态为 completed
    And 客户端可从指定序号继续读取后续事件

  Scenario: 非法状态迁移不产生部分写入
    Given 一个状态为 completed 的 Turn
    When 服务尝试将它迁移为 running
    Then 返回明确的状态迁移错误
    And 状态与事件序号均不变化

  Scenario: 同一任务线程不能并行执行两个 Turn
    Given 一个已经存在活动 Turn 的 Thread
    When 用户再次创建 Turn
    Then 创建请求被拒绝
    And 原 Turn 保持不变

  Scenario: 进程重启后由用户从稳定点恢复
    Given 一个运行中且租约已经过期的 Turn
    When 应用执行启动恢复
    Then Turn 被标记为 interrupted
    And 用户恢复后 Turn 从最后稳定 Checkpoint 继续

  Scenario: 可信沙箱不可用时命令失败关闭
    Given 当前环境没有可信 OS 沙箱
    When Turn 请求执行工作区命令
    Then Harness 拒绝命令执行
    And 拒绝结果明确说明命令能力不可用
