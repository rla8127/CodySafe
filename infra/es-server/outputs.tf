output "instance_id" {
  value = aws_instance.this.id
}

output "ami_name" {
  value = data.aws_ami.ubuntu.name
}

output "public_ip" {
  description = "고정 IP (EIP)"
  value       = aws_eip.this.public_ip
}

output "private_ip" {
  value = aws_instance.this.private_ip
}

output "ssh" {
  value = "ssh -i ~/.ssh/${var.key_name}.pem ubuntu@${aws_eip.this.public_ip}"
}

output "connect_shell" {
  value = "aws ssm start-session --region ${var.region} --target ${aws_instance.this.id}"
}

output "es_url" {
  value = "http://${aws_eip.this.public_ip}:${var.es_port}"
}

output "rag_url" {
  value = "http://${aws_eip.this.public_ip}:${var.rag_port}"
}
