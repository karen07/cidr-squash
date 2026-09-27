# CIDR squash

CIDR squash is a small IPv4 CIDR optimizer that converts an input list into a compact set of output networks.

With the default settings the result is exact: it covers the same IPv4 address set while merging adjacent ranges wherever possible. An optional over-coverage budget allows the optimizer to include a small number of extra addresses in exchange for a substantially shorter CIDR list.

The program is written in C, has no external runtime library dependencies, reads from a file or stdin, writes the optimized list to stdout, and keeps statistics on stderr so it can be used naturally in shell pipelines.

## Описание

CIDR squash - небольшая утилита для оптимизации списков IPv4 CIDR, которая преобразует входной набор сетей в более компактный набор.

С настройками по умолчанию результат точный: он покрывает тот же набор IPv4 адресов и по возможности объединяет соседние диапазоны. Необязательный лимит дополнительного покрытия позволяет включить небольшое число лишних адресов в обмен на заметное сокращение количества CIDR.

Программа написана на C, не требует внешних библиотек при запуске, читает данные из файла или stdin, выводит оптимизированный список в stdout, а статистику - в stderr. Поэтому ее удобно использовать в конвейерах командной строки.

## Сборка

```sh
cmake --preset release
cmake --build --preset release
```

Исполняемый файл:

```text
build/release/cidr-squash
```

## Использование

```text
Commands:
  Optional parameters:
    -p  "0.01"       Maximum allowed over-coverage in percent
                     Default: 0
    -q               Suppress statistics on stderr
    -h               Show help

    "direct.txt"     Input IPv4/CIDR file
                     If omitted or "-", data is read from stdin
```

Точный режим без дополнительного покрытия:

```sh
./build/release/cidr-squash direct.txt > direct_optimized.txt
```

Разрешить до `0.01%` дополнительных IPv4-адресов:

```sh
./build/release/cidr-squash -p 0.01 direct.txt > direct_optimized.txt
```

Через stdin:

```sh
cat direct.txt | ./build/release/cidr-squash -p 0.01 > direct_optimized.txt
```

Оптимизированный список всегда идет в stdout. Статистика - в stderr, поэтому ее можно независимо перенаправлять или отключить через `-q`.

## Что означает over-coverage

При `-p 0` программа строит точное CIDR-представление исходного множества IPv4-адресов. При положительном `-p` разрешено покрыть небольшое число адресов, которых не было во входном наборе, если это позволяет объединить несколько сетей в более крупную.

Например, `-p 0.01` ограничивает число дополнительных адресов бюджетом примерно `0.01%` от количества IPv4-адресов, покрытых точным результатом.

Пример статистики:

```text
input entries:       76411
merged intervals:    20975
exact CIDRs:         33256
output CIDRs:        20652
exact IPv4 covered:  985251381
extra IPv4 covered:  98516
over-coverage:       0.00999907%
budget:              98525 IPv4 (0.01000000%)
trie nodes:          132813
```
