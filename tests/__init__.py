"""测试根包。存在的唯一理由：让 `tests/builtins/` 不与标准库的 `builtins` 撞名——没有它，pytest 会把那个目录当成顶层包 `builtins`，而 `sys.modules` 里那个位置早已被标准库占住。"""
