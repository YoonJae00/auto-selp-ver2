import PillButton from '@/components/UI/PillButton/PillButton';
import styles from './marketing.module.css';

export default function LandingPage() {
  return (
    <main className={styles.hero}>
      <h1>이커머스 운영의 새로운 정의.</h1>
      <p>당신의 쇼핑몰을 AI와 함께 가장 스마트하게 관리하세요.</p>
      <PillButton>지금 시작하기</PillButton>
    </main>
  );
}
