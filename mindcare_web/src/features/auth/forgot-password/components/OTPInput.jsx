import CodeInput from '../../../../components/CodeInput/CodeInput';

export default function OTPInput({ value, onChange, error }) {
  return <CodeInput value={value} onChange={onChange} error={error} />;
}
