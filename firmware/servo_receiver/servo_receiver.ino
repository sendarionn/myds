// "P=95,T=82\n" を受信して2軸サーボへ角度を指示する
// 最初の有効な指示を受け取るまでサーボを attach しない（起動直後に勝手に動かさないため）
#include <Servo.h>  // ESP32 の場合は ESP32Servo.h に置き換える

const int PAN_PIN = 9;
const int TILT_PIN = 10;

Servo panServo;
Servo tiltServo;
bool attached = false;
char buf[32];
size_t len = 0;

void apply(const char* line) {
  int p, t;
  if (sscanf(line, "P=%d,T=%d", &p, &t) != 2) return;
  p = constrain(p, 0, 180);
  t = constrain(t, 0, 180);
  if (!attached) {
    panServo.write(p);  // attach 前に初期角度を設定する
    tiltServo.write(t);
    panServo.attach(PAN_PIN);
    tiltServo.attach(TILT_PIN);
    attached = true;
  }
  panServo.write(p);
  tiltServo.write(t);
}

void setup() {
  Serial.begin(115200);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      buf[len] = '\0';
      apply(buf);
      len = 0;
    } else if (c != '\r' && len < sizeof(buf) - 1) {
      buf[len++] = c;
    }
  }
}
