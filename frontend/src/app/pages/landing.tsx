import { Link } from "react-router";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "../components/ui/accordion";
import { Badge } from "../components/ui/badge";
import { Check, Settings, Bot, Lock, ArrowRight, Sparkles } from "lucide-react";

export function LandingPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50">
      {/* Navigation */}
      <nav className="border-b bg-white/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl flex items-center justify-center text-2xl shadow-lg shadow-indigo-200">
              🌀
            </div>
            <div>
              <div className="font-bold text-lg bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">媒力</div>
              <div className="text-xs text-muted-foreground">MediaFlow</div>
            </div>
          </div>
          <div className="flex items-center gap-6">
            <a href="#features" className="text-sm hover:text-indigo-600 transition-colors hidden md:block">功能介绍</a>
            <a href="#pricing" className="text-sm hover:text-indigo-600 transition-colors hidden md:block">价格</a>
            <Link to="/auth">
              <Button variant="ghost" size="sm">登录</Button>
            </Link>
            <Link to="/auth">
              <Button size="sm" className="bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 shadow-lg shadow-indigo-200">
                免费试用
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="container mx-auto px-4 py-20 md:py-32">
        <div className="max-w-4xl mx-auto text-center space-y-8">
          <Badge variant="secondary" className="bg-indigo-100 text-indigo-700 border-indigo-200 px-4 py-1">
            <Sparkles className="w-3 h-3 mr-1 inline" />
            AI 驱动的自媒体运营
          </Badge>
          <h1 className="text-5xl md:text-7xl font-bold bg-gradient-to-r from-indigo-600 via-purple-600 to-indigo-600 bg-clip-text text-transparent leading-tight">
            自媒体的力量
          </h1>
          <p className="text-xl md:text-2xl text-muted-foreground max-w-2xl mx-auto">
            AI 自动运营小红书，让每个老板都有一位专属的数字员工
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center pt-4">
            <Link to="/auth">
              <Button size="lg" className="bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 shadow-xl shadow-indigo-200 text-lg px-8 py-6 group">
                立即免费试用
                <ArrowRight className="ml-2 w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </Button>
            </Link>
            <Button size="lg" variant="outline" className="text-lg px-8 py-6">
              观看演示
            </Button>
          </div>
          <p className="text-sm text-muted-foreground">
            🎉 7 天免费试用 · 无需信用卡 · 随时取消
          </p>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="container mx-auto px-4 py-20 bg-white/50 rounded-3xl my-20">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-bold mb-4">为什么选择媒力？</h2>
            <p className="text-xl text-muted-foreground">让 AI 成为你的专属运营官</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            <Card className="border-2 hover:border-indigo-200 hover:shadow-xl transition-all duration-300">
              <CardHeader>
                <div className="w-14 h-14 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-2xl flex items-center justify-center mb-4 shadow-lg shadow-indigo-200">
                  <Settings className="w-7 h-7 text-white" />
                </div>
                <CardTitle>全自动运营</CardTitle>
                <CardDescription className="text-base">
                  从内容创作到发布，完全自动化。设定一次，持续运转。
                </CardDescription>
              </CardHeader>
            </Card>

            <Card className="border-2 hover:border-purple-200 hover:shadow-xl transition-all duration-300">
              <CardHeader>
                <div className="w-14 h-14 bg-gradient-to-br from-purple-500 to-pink-600 rounded-2xl flex items-center justify-center mb-4 shadow-lg shadow-purple-200">
                  <Bot className="w-7 h-7 text-white" />
                </div>
                <CardTitle>AI 智能创作</CardTitle>
                <CardDescription className="text-base">
                  小媒会学习你的风格，生成符合你品牌调性的优质内容。
                </CardDescription>
              </CardHeader>
            </Card>

            <Card className="border-2 hover:border-indigo-200 hover:shadow-xl transition-all duration-300">
              <CardHeader>
                <div className="w-14 h-14 bg-gradient-to-br from-indigo-600 to-blue-600 rounded-2xl flex items-center justify-center mb-4 shadow-lg shadow-blue-200">
                  <Lock className="w-7 h-7 text-white" />
                </div>
                <CardTitle>用户自带账号</CardTitle>
                <CardDescription className="text-base">
                  使用自己的小红书账号，数据和粉丝永远属于你。
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section id="pricing" className="container mx-auto px-4 py-20">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-bold mb-4">简单透明的价格</h2>
            <p className="text-xl text-muted-foreground">选择适合你的方案</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {/* Basic Plan */}
            <Card className="border-2 hover:shadow-xl transition-all duration-300">
              <CardHeader>
                <CardTitle>基础版</CardTitle>
                <CardDescription>适合个人创作者</CardDescription>
                <div className="mt-4">
                  <span className="text-4xl font-bold">¥99</span>
                  <span className="text-muted-foreground">/月</span>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <ul className="space-y-3">
                  <li className="flex items-start gap-2">
                    <Check className="w-5 h-5 text-green-600 mt-0.5 flex-shrink-0" />
                    <span>每天 1 篇自动发布</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <Check className="w-5 h-5 text-green-600 mt-0.5 flex-shrink-0" />
                    <span>AI 内容生成</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <Check className="w-5 h-5 text-green-600 mt-0.5 flex-shrink-0" />
                    <span>基础数据分析</span>
                  </li>
                </ul>
                <Button variant="outline" className="w-full mt-6">选择基础版</Button>
              </CardContent>
            </Card>

            {/* Pro Plan */}
            <Card className="border-2 border-indigo-500 hover:shadow-2xl transition-all duration-300 relative overflow-hidden">
              <div className="absolute top-0 right-0 bg-gradient-to-br from-indigo-500 to-purple-600 text-white text-xs px-4 py-1 rounded-bl-lg">
                推荐
              </div>
              <CardHeader>
                <CardTitle>专业版</CardTitle>
                <CardDescription>适合专业运营者</CardDescription>
                <div className="mt-4">
                  <span className="text-4xl font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">¥199</span>
                  <span className="text-muted-foreground">/月</span>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <ul className="space-y-3">
                  <li className="flex items-start gap-2">
                    <Check className="w-5 h-5 text-green-600 mt-0.5 flex-shrink-0" />
                    <span>每天 3 篇自动发布</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <Check className="w-5 h-5 text-green-600 mt-0.5 flex-shrink-0" />
                    <span>高级 AI 内容生成</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <Check className="w-5 h-5 text-green-600 mt-0.5 flex-shrink-0" />
                    <span>深度数据分析</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <Check className="w-5 h-5 text-green-600 mt-0.5 flex-shrink-0" />
                    <span>优先客服支持</span>
                  </li>
                </ul>
                <Button className="w-full mt-6 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700">
                  选择专业版
                </Button>
              </CardContent>
            </Card>

            {/* Enterprise Plan */}
            <Card className="border-2 hover:shadow-xl transition-all duration-300">
              <CardHeader>
                <CardTitle>企业版</CardTitle>
                <CardDescription>适合团队和企业</CardDescription>
                <div className="mt-4">
                  <span className="text-4xl font-bold">¥299</span>
                  <span className="text-muted-foreground">/月</span>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <ul className="space-y-3">
                  <li className="flex items-start gap-2">
                    <Check className="w-5 h-5 text-green-600 mt-0.5 flex-shrink-0" />
                    <span>无限自动发布</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <Check className="w-5 h-5 text-green-600 mt-0.5 flex-shrink-0" />
                    <span>定制化 AI 训练</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <Check className="w-5 h-5 text-green-600 mt-0.5 flex-shrink-0" />
                    <span>多账号管理</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <Check className="w-5 h-5 text-green-600 mt-0.5 flex-shrink-0" />
                    <span>专属客户经理</span>
                  </li>
                </ul>
                <Button variant="outline" className="w-full mt-6">选择企业版</Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* FAQ Section */}
      <section className="container mx-auto px-4 py-20 bg-white/50 rounded-3xl my-20">
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-bold mb-4">常见问题</h2>
            <p className="text-xl text-muted-foreground">快速了解媒力</p>
          </div>
          <Accordion type="single" collapsible className="space-y-4">
            <AccordionItem value="item-1" className="bg-white rounded-lg px-6 border">
              <AccordionTrigger className="hover:no-underline">
                媒力是如何工作的？
              </AccordionTrigger>
              <AccordionContent className="text-muted-foreground">
                媒力通过 AI 助手"小媒"与你对话，学习你的内容偏好和风格。然后自动从你指定的内容源抓取素材，生成符合你品牌调性的内容，并按照你设定的时间自动发布到小红书。
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="item-2" className="bg-white rounded-lg px-6 border">
              <AccordionTrigger className="hover:no-underline">
                我需要提供小红书账号密码吗？
              </AccordionTrigger>
              <AccordionContent className="text-muted-foreground">
                是的，为了实现自动发布功能，需要你授权绑定小红书账号。我们采用加密存储，确保你的账号安全。你的数据和粉丝始终属于你自己。
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="item-3" className="bg-white rounded-lg px-6 border">
              <AccordionTrigger className="hover:no-underline">
                AI 生成的内容质量如何？
              </AccordionTrigger>
              <AccordionContent className="text-muted-foreground">
                小媒会学习你的写作风格和偏好，生成的内容会越来越符合你的品牌调性。每次发布前都会有预览确认环节，你可以选择通过、修改或重新生成。
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="item-4" className="bg-white rounded-lg px-6 border">
              <AccordionTrigger className="hover:no-underline">
                可以随时取消订阅吗？
              </AccordionTrigger>
              <AccordionContent className="text-muted-foreground">
                当然可以。我们提供灵活的订阅方式，你可以随时在用户中心取消订阅，不会有任何额外费用。
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="item-5" className="bg-white rounded-lg px-6 border">
              <AccordionTrigger className="hover:no-underline">
                有技术支持吗？
              </AccordionTrigger>
              <AccordionContent className="text-muted-foreground">
                所有付费用户都享有技术支持服务。专业版和企业版用户可获得优先支持，企业版用户还配有专属客户经理。
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </div>
      </section>

      {/* CTA Section */}
      <section className="container mx-auto px-4 py-20">
        <div className="max-w-4xl mx-auto bg-gradient-to-r from-indigo-500 to-purple-600 rounded-3xl p-12 md:p-16 text-center text-white shadow-2xl shadow-indigo-200">
          <h2 className="text-4xl md:text-5xl font-bold mb-6">
            准备好开始了吗？
          </h2>
          <p className="text-xl mb-8 opacity-90">
            加入数千位内容创作者，让 AI 帮你运营自媒体
          </p>
          <Link to="/auth">
            <Button size="lg" variant="secondary" className="text-lg px-8 py-6 bg-white text-indigo-600 hover:bg-gray-100 shadow-xl">
              立即开始 7 天免费试用
              <ArrowRight className="ml-2 w-5 h-5" />
            </Button>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t bg-white/80 backdrop-blur-sm mt-20">
        <div className="container mx-auto px-4 py-12">
          <div className="grid md:grid-cols-4 gap-8">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-lg flex items-center justify-center text-xl">
                  🌀
                </div>
                <div>
                  <div className="font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">媒力</div>
                  <div className="text-xs text-muted-foreground">MediaFlow</div>
                </div>
              </div>
              <p className="text-sm text-muted-foreground">
                自媒体的力量，让每个创作者都能轻松运营。
              </p>
            </div>
            <div>
              <h4 className="font-semibold mb-4">产品</h4>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li><a href="#features" className="hover:text-indigo-600 transition-colors">功能介绍</a></li>
                <li><a href="#pricing" className="hover:text-indigo-600 transition-colors">价格方案</a></li>
                <li><a href="#" className="hover:text-indigo-600 transition-colors">使用案例</a></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-4">支持</h4>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li><a href="#" className="hover:text-indigo-600 transition-colors">帮助中心</a></li>
                <li><a href="#" className="hover:text-indigo-600 transition-colors">联系我们</a></li>
                <li><a href="#" className="hover:text-indigo-600 transition-colors">服务状态</a></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-4">法律</h4>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li><a href="#" className="hover:text-indigo-600 transition-colors">服务条款</a></li>
                <li><a href="#" className="hover:text-indigo-600 transition-colors">隐私政策</a></li>
                <li><a href="#" className="hover:text-indigo-600 transition-colors">Cookie 政策</a></li>
              </ul>
            </div>
          </div>
          <div className="border-t mt-12 pt-8 text-center text-sm text-muted-foreground">
            <p>© 2026 媒力 MediaFlow. 保留所有权利。</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
