# CIDR squash

CIDR squash minimizes lists of IPv4 networks. By default, it preserves the exact address
set; an optional over-coverage budget can reduce the number of output CIDRs further.

## Описание

CIDR squash сокращает списки IPv4-сетей. По умолчанию программа сохраняет точно то же
множество адресов; необязательный лимит дополнительного покрытия позволяет ещё сильнее
уменьшить число выходных CIDR.

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
