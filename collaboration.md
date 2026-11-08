# Синхронна робота агентів над базою знань

Цей файл задає обов’язковий Git-протокол для всіх агентів і checkout-ів. Спільна KB існує тільки в orphan-гілці `kb-only` remote `origin`; каталог `knowledge-base/` є linked worktree цієї гілки. Не припускай, що локальний checkout актуальний або що інший агент уже запушив зміни.

## Основні гарантії

1. Перед читанням KB отримай останній `origin/kb-only`.
2. Перед редагуванням перевір локальні незакомічені зміни; ніколи не викидай і не перезаписуй їх.
3. Перед комітом ще раз отримай remote; перед push інтегруй усі нові коміти.
4. Після кожного значущого оновлення пуш у `origin/kb-only` та перевір, що remote вказує на потрібний commit.
5. Розробника не питають про merge-конфлікти, застарілий текст, дублікати чи редакційні суперечності. Агент сам перевіряє джерела, об’єднує знання або точно позначає, що лишилося невідомим.
6. Force push, reset історії, видалення чужих чернеток і merge KB у `main` заборонені.

## Початок задачі: pull перед читанням

Спочатку переконайся, що ти в KB worktree та гілці:

```bash
git -C knowledge-base rev-parse --show-toplevel
git -C knowledge-base branch --show-current
git -C knowledge-base status --short --branch
```

Очікувана гілка — `kb-only`; remote `origin` має бути `https://github.com/VladislavCalculus/Muliprosessing-Analisis.git`. Потім:

```bash
git -C knowledge-base fetch origin refs/heads/kb-only:refs/remotes/origin/kb-only
git -C knowledge-base rev-list --left-right --count HEAD...origin/kb-only
```

Числа виводяться як `local-only remote-only`:

- `0 N`: локальний branch позаду; якщо worktree чистий, виконай `git -C knowledge-base merge --ff-only origin/kb-only`.
- `0 0`: branch уже синхронізований; merge не запускай.
- `N 0`: локально є коміти для публікації; прочитай їх diff і log перед подальшою роботою.
- `N M`, обидва числа більші за нуль: branch розійшовся; спершу звір граф та tree, потім rebase локальні коміти на remote за процедурою нижче.
- Fetch не вдався: не роби вигляд, що KB актуальна. Перевір remote, мережу й Git credentials; зроби безпечні локальні зміни, якщо можливо, і повідом точний зовнішній блокер лише після вичерпання самостійних кроків.

Після оновлення прочитай `README.md`, `status.md`, цей файл і предметні сторінки. Не покладайся на вміст, який був у контексті до fetch.

## Кілька агентів в одному фізичному checkout

Якщо `knowledge-base/` має незакомічені чи staged зміни, вважай їх чужою/паралельною роботою, доки не доведено протилежне. Переглянь diff і не чіпай відповідні фрагменти. Для роботи, що може перетинатися з такими змінами, відкрий окремий detached worktree на актуальному remote:

```bash
mkdir -p .codex/kb-worktrees
git worktree add --detach .codex/kb-worktrees/<унікальний-id-задачі> origin/kb-only
```

Працюй у ньому замість спільної папки. `<унікальний-id-задачі>` має бути унікальним для агента/задачі (наприклад короткий slug плюс PID). Каталог `.codex/` ігнорується кореневим Git. Не створюй для нього окремий clone чи окремий remote.

Після завершення у detached worktree зроби коміт, інтегруй актуальний remote, запуш його в `kb-only`, перевір hash, а потім прибери власний чистий worktree:

```bash
git -C .codex/kb-worktrees/<унікальний-id-задачі> fetch origin refs/heads/kb-only:refs/remotes/origin/kb-only
git -C .codex/kb-worktrees/<унікальний-id-задачі> rebase origin/kb-only
git -C .codex/kb-worktrees/<унікальний-id-задачі> push origin HEAD:refs/heads/kb-only
git ls-remote origin refs/heads/kb-only
git worktree remove .codex/kb-worktrees/<унікальний-id-задачі>
```

Якщо робота в `knowledge-base/` чиста, можна редагувати її напряму. Не запускай два агенти на редагування того самого файла в одній незакоміченій worktree; розділяй роботу по документах або використовуй окремі worktree.

Для Jira delivery застосовуй ті самі межі володіння: read-only fetch/planning може бути паралельним, але один implementer володіє спільною кодовою worktree за раз; reviewer читає завершений diff після implementer; Jira reporter/updater працюють після визначених gates і лише у вибраних MLT issues. Не запускай одночасно два Jira writers на ті самі keys. KB edits зводить координатор за процедурою нижче і публікує їх лише у `kb-only`.

## Злиття комітів, push rejection і Markdown-конфлікти

Коли push відхилений через нові remote-коміти, збережи власний коміт і виконай:

```bash
git -C <kb-worktree> fetch origin refs/heads/kb-only:refs/remotes/origin/kb-only
git -C <kb-worktree> rebase origin/kb-only
```

Якщо виник conflict:

1. `git status` та `git diff --cc` покажуть уражені файли й контекст.
2. Для кожного файла прочитай обидві повні версії, історію (`git log --oneline -- <файл>`) і conflict stages (`git show :1:<файл>`, `:2:`, `:3:` коли доступні). Не вибирай механічно `ours` чи `theirs` для всього документа.
3. Злий сумісні факти, прибери лише доведені дублікати/застарілі формулювання, збережи джерело й дату для спірних тверджень.
4. Перевір, що файл не втратив унікальні розділи, посилання, Jira keys чи актуальні відкриті питання. Потім `git add <файли>` і `git rebase --continue`.
5. Повтори цикл, доки rebase не завершиться; зроби `git diff --check`, переглянь увесь результат і пуш звичайним fast-forward push.

Правила вибору змісту:

- Фактичну поведінку реалізованого коду звіряй із поточним checkout; поточний Jira-стан — із live Jira, коли доступна; звітні скриншоти залишаються датованими історичними свідченнями.
- `status.md` є замінюваним snapshot: зведи туди найновіший підтверджений стан, але збережи невирішені ризики й попередні непідтверджені факти, якщо вони досі важливі.
- `changes.md` є append-only дайджестом: додавай датований запис, не стирай історію та не переписуй старий запис, окрім виправлення доведеної фактичної помилки з приміткою.
- Вимоги/факти з різних агентів, які не суперечать одне одному, об’єднуй. Якщо версії суперечать одна одній, шукай першоджерело. Якщо перевірка не знімає конфлікт, зафіксуй обидва свідчення, їхні джерела й дату та явно напиши «не встановлено»; не вигадуй компромісний факт і не став питання розробнику.
- При delete/modify конфлікті за замовчуванням збережи документ і інтегруй нове знання. Видаляй KB-сторінку лише якщо підтверджено, що вона дублює іншу та вся її унікальна інформація вже перенесена.
- Перевір `git merge-base HEAD origin/kb-only`. Якщо в межах `kb-only` немає спільного предка, порівняй обидва корені та переконайся, що в них тільки KB. Для відновлення збережи обидва дерева й злий remote через `git merge --allow-unrelated-histories origin/kb-only`, розв’яжи конфлікти та створи merge commit на `kb-only`. Орphan-відмінність `kb-only` від `main` очікувана; `main` не є учасником цього merge.

Після успішного rebase/merge:

```bash
git -C <kb-worktree> status --short --branch
git -C <kb-worktree> diff --check
git -C <kb-worktree> push origin HEAD:refs/heads/kb-only
git ls-remote origin refs/heads/kb-only
```

Якщо інший агент встиг запушити знову, повтори fetch → rebase/merge → conflict resolution → push. Повторюй, доки push не пройде, а remote hash не дорівнюватиме твоєму `HEAD`. Не переписуй remote історію, щоб обійти гонку.

## Завершення задачі

- Предметні факти внесені у відповідну сторінку, а не залишені лише в чаті.
- `status.md` оновлений за потреби; `changes.md` має датований дайджест значущих змін.
- У staged diff тільки intended KB Markdown; немає credentials, персональних даних, коду чи файлів із `main`.
- Після останнього fetch всі нові remote коміти інтегровані, push успішний, `origin/kb-only` hash збігається з опублікованим `HEAD`.
- Якщо агент не має прав/мережі для push, збережи коміт локально, зафіксуй precise blocker у handover та заверши всі інші можливі частини. Це єдиний випадок, коли локальна KB може залишитися не опублікованою без рішення самого агента.
