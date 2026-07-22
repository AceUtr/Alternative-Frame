# Final Evidence

- 实现文件：`calculator.py`
  - 提供可由外部代码导入调用的 `add(left, right)` 函数，并返回两个数的加法结果。
- 测试文件：`test_calculator.py`
  - 覆盖正数、负数、零和浮点数加法场景；浮点断言使用 `pytest.approx`。
- 执行命令：`pytest -q`
- 退出码：`0`
- 测试结果：`45 passed in 0.27s`，全部测试通过，无失败。
