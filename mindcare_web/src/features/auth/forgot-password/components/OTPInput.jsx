import CodeInput from '../../../../components/CodeInput/CodeInput';

export default function OTPInput({ value, onChange, error, describedBy, ref }) {
  return (
    <CodeInput ref={ref} value={value} onChange={onChange} error={error} describedBy={describedBy} />
  );
}
