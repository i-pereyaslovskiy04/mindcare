import { useState } from 'react';
import TaskItem from './components/TaskItem';
import styles from './TasksPage.module.css';

const INITIAL_TASKS = [
  {
    id: 1,
    title: 'Дневник эмоций — 5 дней подряд',
    desc: 'Минимум одна запись в день, можно короткую. Цель — расширить словарь чувств.',
    done: false,
    urgent: false,
    due: 'до пятницы',
    tag: 'Самонаблюдение',
    comment: 'Хорошо идёте — не торопитесь и не ругайте себя за пропуски.',
  },
  {
    id: 2,
    title: 'Дыхательная практика 4-7-8 перед сном',
    desc: '5 циклов вечером. Замечать, как меняются ощущения в теле и качество засыпания.',
    done: false,
    urgent: true,
    due: 'каждый день',
    tag: 'Тело и сон',
    comment: null,
  },
  {
    id: 3,
    title: 'Написать три вещи, за которые благодарны',
    desc: 'Раз в день, в любое время. Можно мелкие — кофе, тишина, чужая улыбка.',
    done: true,
    urgent: false,
    due: 'ежедневно',
    tag: 'Практика благодарности',
    comment: null,
  },
  {
    id: 4,
    title: 'Прочитать главу «Внутренний критик»',
    desc: 'Из подборки материалов. После — записать одну мысль, которую заметили.',
    done: true,
    urgent: false,
    due: 'до 25 апреля',
    tag: 'Когнитивная работа',
    comment: null,
  },
];

function StatTile({ label, value, sub }) {
  return (
    <div className={styles.statTile}>
      <div className={styles.statLabel}>{label}</div>
      <div className={styles.statNum}>
        {value}
        {sub && <em>{sub}</em>}
      </div>
    </div>
  );
}

function TaskGroup({ title, count, tasks, onToggle }) {
  if (tasks.length === 0) return null;
  return (
    <div className={styles.group}>
      <h2 className={styles.groupTitle}>
        {title}
        <span className={styles.groupCount}>· {count}</span>
      </h2>
      {tasks.map((task) => (
        <TaskItem key={task.id} task={task} onToggle={onToggle} />
      ))}
    </div>
  );
}

export default function TasksPage() {
  const [tasks, setTasks] = useState(INITIAL_TASKS);

  function toggle(id) {
    setTasks((prev) =>
      prev.map((t) => (t.id === id ? { ...t, done: !t.done } : t))
    );
  }

  const active = tasks.filter((t) => !t.done);
  const done   = tasks.filter((t) => t.done);

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>
        Задания от <em>психолога</em>
      </h1>
      <p className={styles.pageSub}>
        Небольшие практики между сессиями. Отмечайте по мере выполнения — специалист видит ваш прогресс.
      </p>

      <div className={styles.stats}>
        <StatTile label="Активных заданий"    value={active.length} sub=" задач" />
        <StatTile label="Выполнено"           value={done.length}   sub={` из ${tasks.length}`} />
        <StatTile label="До следующей сессии" value="2"             sub=" дня" />
      </div>

      <TaskGroup
        title="В процессе"
        count={active.length}
        tasks={active}
        onToggle={toggle}
      />
      <TaskGroup
        title="Выполнено"
        count={done.length}
        tasks={done}
        onToggle={toggle}
      />
    </div>
  );
}
